from __future__ import annotations

import logging
import socket
import struct
import threading
from dataclasses import dataclass

MDNS_GROUP = "224.0.0.251"
MDNS_PORT = 5353
MDNS_TTL_SECONDS = 120
DNS_TYPE_A = 1
DNS_TYPE_ANY = 255
DNS_CLASS_IN = 1
DNS_CLASS_CACHE_FLUSH_IN = 0x8001

logger = logging.getLogger(__name__)


class MdnsResponderError(RuntimeError):
    pass


@dataclass(frozen=True)
class MdnsResponder:
    name: str
    port: int
    address: str
    _socket: socket.socket
    _stop: threading.Event
    _thread: threading.Thread

    def close(self) -> None:
        self._stop.set()
        try:
            self._socket.close()
        except OSError:
            pass
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    @property
    def url(self) -> str:
        return f"http://{self.name}:{self.port}"


@dataclass(frozen=True)
class DnsQuestion:
    name: str
    qtype: int
    qclass: int
    unicast_response: bool


def start_mdns_responder(name: str, port: int) -> MdnsResponder | None:
    normalized_name = normalize_mdns_name(name)
    try:
        address = detect_lan_ipv4()
        responder = _create_responder(normalized_name, port, address)
    except Exception as exc:
        logger.warning("mDNS disabled for %s: %s", normalized_name, exc)
        return None

    responder._thread.start()
    _send_announcement(responder)
    logger.info("mDNS name available on local network: %s", responder.url)
    return responder


def normalize_mdns_name(value: str) -> str:
    name = (value or "").strip().rstrip(".")
    if not name:
        raise MdnsResponderError("mDNS name is empty.")
    if not name.lower().endswith(".local"):
        name = f"{name}.local"
    labels = name.split(".")
    if any(not label for label in labels):
        raise MdnsResponderError(f"{value!r} is not a valid mDNS name.")
    return ".".join(label.lower() for label in labels)


def detect_lan_ipv4() -> str:
    for target in ("8.8.8.8", "1.1.1.1", MDNS_GROUP):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((target, 80))
                address = sock.getsockname()[0]
                if not address.startswith("127."):
                    return address
        except OSError:
            pass
    try:
        address = socket.gethostbyname(socket.gethostname())
    except OSError as exc:
        raise MdnsResponderError("could not detect a LAN IPv4 address.") from exc
    if address.startswith("127."):
        raise MdnsResponderError("only loopback IPv4 address was detected.")
    return address


def _create_responder(name: str, port: int, address: str) -> MdnsResponder:
    stop = threading.Event()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        sock.bind(("", MDNS_PORT))
        membership = socket.inet_aton(MDNS_GROUP) + socket.inet_aton("0.0.0.0")
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        sock.settimeout(0.5)
    except OSError:
        sock.close()
        raise

    responder = MdnsResponder(
        name=name,
        port=port,
        address=address,
        _socket=sock,
        _stop=stop,
        _thread=threading.Thread(target=_serve, args=(sock, stop, name, address), daemon=True),
    )
    return responder


def _serve(sock: socket.socket, stop: threading.Event, name: str, address: str) -> None:
    while not stop.is_set():
        try:
            data, sender = sock.recvfrom(9000)
        except socket.timeout:
            continue
        except TimeoutError:
            continue
        except OSError:
            break

        questions = list(_questions_from_packet(data))
        matching = [
            question
            for question in questions
            if question.name == name and question.qtype in {DNS_TYPE_A, DNS_TYPE_ANY}
        ]
        if not matching:
            continue

        response = _build_a_response(name, address, query_id=b"\x00\x00")
        try:
            if any(question.unicast_response for question in matching):
                sock.sendto(_build_a_response(name, address, query_id=data[:2]), sender)
            sock.sendto(response, (MDNS_GROUP, MDNS_PORT))
        except OSError:
            logger.debug("Could not send mDNS response for %s", name, exc_info=True)


def _send_announcement(responder: MdnsResponder) -> None:
    try:
        responder._socket.sendto(
            _build_a_response(responder.name, responder.address, query_id=b"\x00\x00"),
            (MDNS_GROUP, MDNS_PORT),
        )
    except OSError:
        logger.debug("Could not send initial mDNS announcement for %s", responder.name, exc_info=True)


def _questions_from_packet(data: bytes) -> list[DnsQuestion]:
    if len(data) < 12:
        return []
    qdcount = struct.unpack("!H", data[4:6])[0]
    offset = 12
    questions: list[DnsQuestion] = []
    for _ in range(qdcount):
        try:
            name, offset = _read_name(data, offset)
            qtype, raw_qclass = struct.unpack("!HH", data[offset : offset + 4])
        except (IndexError, struct.error, ValueError):
            return questions
        offset += 4
        questions.append(
            DnsQuestion(
                name=name,
                qtype=qtype,
                qclass=raw_qclass & 0x7FFF,
                unicast_response=bool(raw_qclass & 0x8000),
            )
        )
    return questions


def _read_name(data: bytes, offset: int) -> tuple[str, int]:
    labels: list[str] = []
    next_offset = offset
    jumped = False
    seen_offsets: set[int] = set()
    while True:
        if offset >= len(data):
            raise ValueError("DNS name exceeds packet length.")
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(data):
                raise ValueError("DNS pointer exceeds packet length.")
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            if pointer in seen_offsets:
                raise ValueError("DNS name has a pointer loop.")
            seen_offsets.add(pointer)
            if not jumped:
                next_offset = offset + 2
            offset = pointer
            jumped = True
            continue
        offset += 1
        label = data[offset : offset + length]
        if len(label) != length:
            raise ValueError("DNS label exceeds packet length.")
        labels.append(label.decode("ascii", errors="ignore").lower())
        offset += length
    return ".".join(labels), (next_offset if jumped else offset)


def _build_a_response(name: str, address: str, query_id: bytes) -> bytes:
    encoded_name = _encode_name(name)
    header = query_id[:2] + struct.pack("!HHHHH", 0x8400, 0, 1, 0, 0)
    answer = (
        encoded_name
        + struct.pack("!HHIH", DNS_TYPE_A, DNS_CLASS_CACHE_FLUSH_IN, MDNS_TTL_SECONDS, 4)
        + socket.inet_aton(address)
    )
    return header + answer


def _encode_name(name: str) -> bytes:
    labels = name.rstrip(".").split(".")
    encoded = bytearray()
    for label in labels:
        raw = label.encode("ascii")
        if not raw or len(raw) > 63:
            raise MdnsResponderError(f"{name!r} has an invalid DNS label.")
        encoded.append(len(raw))
        encoded.extend(raw)
    encoded.append(0)
    return bytes(encoded)
