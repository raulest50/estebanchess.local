import socket
import struct

from chess_move_analyzer.mdns import (
    DNS_CLASS_IN,
    DNS_TYPE_A,
    DNS_TYPE_ANY,
    normalize_mdns_name,
    _build_a_response,
    _encode_name,
    _questions_from_packet,
)


def test_normalize_mdns_name_adds_local_suffix_and_lowercases():
    assert normalize_mdns_name("Chess109") == "chess109.local"
    assert normalize_mdns_name("Chess109.local.") == "chess109.local"


def test_questions_from_packet_parses_mdns_question():
    packet = _query_packet("chess109.local", DNS_TYPE_A, DNS_CLASS_IN | 0x8000)

    questions = _questions_from_packet(packet)

    assert len(questions) == 1
    assert questions[0].name == "chess109.local"
    assert questions[0].qtype == DNS_TYPE_A
    assert questions[0].qclass == DNS_CLASS_IN
    assert questions[0].unicast_response is True


def test_build_a_response_contains_ipv4_answer():
    response = _build_a_response("chess109.local", "192.168.1.50", query_id=b"\x12\x34")

    assert response[:2] == b"\x12\x34"
    flags, qdcount, ancount, nscount, arcount = struct.unpack("!HHHHH", response[2:12])
    assert flags == 0x8400
    assert qdcount == 0
    assert ancount == 1
    assert nscount == 0
    assert arcount == 0
    assert socket.inet_aton("192.168.1.50") in response


def test_questions_from_packet_accepts_any_query_type():
    packet = _query_packet("chess109.local", DNS_TYPE_ANY, DNS_CLASS_IN)

    questions = _questions_from_packet(packet)

    assert questions[0].qtype == DNS_TYPE_ANY
    assert questions[0].unicast_response is False


def _query_packet(name: str, qtype: int, qclass: int) -> bytes:
    header = b"\x00\x00" + struct.pack("!HHHHH", 0, 1, 0, 0, 0)
    question = _encode_name(name) + struct.pack("!HH", qtype, qclass)
    return header + question
