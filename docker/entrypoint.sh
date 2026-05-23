#!/usr/bin/env sh
set -eu

start_mdns() {
    hostname="${MDNS_HOSTNAME:-estebanchess}"
    port="${CHESS_ANALYZER_PORT:-8080}"

    echo "${hostname}" > /etc/hostname || true
    mkdir -p /run/dbus /etc/avahi/services

    if [ ! -s /etc/machine-id ] && command -v dbus-uuidgen >/dev/null 2>&1; then
        dbus-uuidgen > /etc/machine-id || true
    fi

    rm -f /run/dbus/pid
    if command -v dbus-daemon >/dev/null 2>&1; then
        dbus-daemon --system --fork || echo "Warning: dbus-daemon did not start; mDNS may be unavailable."
    fi

    cat > /etc/avahi/avahi-daemon.conf <<EOF
[server]
host-name=${hostname}
domain-name=local
use-ipv4=yes
use-ipv6=yes

[wide-area]
enable-wide-area=no

[publish]
publish-addresses=yes
publish-hinfo=yes
publish-workstation=yes
publish-domain=yes

[reflector]
enable-reflector=no
EOF

    cat > /etc/avahi/services/chess-move-analyzer.service <<EOF
<?xml version="1.0" standalone="no"?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">Chess Move Analyzer on %h</name>
  <service>
    <type>_http._tcp</type>
    <port>${port}</port>
  </service>
</service-group>
EOF

    if command -v avahi-daemon >/dev/null 2>&1; then
        avahi-daemon --daemonize --no-drop-root || echo "Warning: avahi-daemon did not start; use localhost or the host IP instead."
    fi
}

case "${ENABLE_MDNS:-0}" in
    1|true|TRUE|yes|YES|on|ON)
        start_mdns
        ;;
esac

exec "$@"
