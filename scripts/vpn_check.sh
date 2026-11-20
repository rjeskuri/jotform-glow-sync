#!/bin/sh
# Is a VPN on? Salesforce freezes a user whose API call comes through one (2026-09-30), so a
# session runs this as its own call before any sf command (CLAUDE.md rule 12; the settings
# allow it alone, with no prompt), and glow/salesforce.py require_vpn_off runs it before every
# tool's Salesforce call, --vpn-off or not (ticket #251).
#
# Read-only: `route -n get default` and `ifconfig -a`, nothing else. A VPN is on when the
# default route goes through a tunnel, or a tunnel holds an IPv4 address (a split tunnel: the
# default stays on en0). A tunnel is known by its KIND, never by its address: a point-to-point
# interface, or one named utun, ppp, ipsec, tun, tap, gpd or wg. macOS lists utun0..utun7
# with only IPv6 addresses while the VPN is off; an Ethernet, Wi-Fi or bridge interface (en*,
# bridge*) on 10.x or 172.16-31.x is a LAN.
#
#   vpn: off             exit 0
#   vpn: on <iface>      exit 1 (the first tunnel found, and why)
#   vpn: unknown (...)   on standard error, exit 2: the state could not be read (no default
#                        route, ifconfig failed) - never `vpn: off` then: it fails closed
set -u
PATH=$PATH:/sbin:/usr/sbin      # route and ifconfig, found by name: /sbin on macOS
LC_ALL=C
export PATH LC_ALL

unknown() { echo "vpn: unknown ($1)" >&2; exit 2; }
[ $# -eq 0 ] || unknown "it takes no arguments: scripts/vpn_check.sh"

tunnel_name() {
  case "$1" in utun* | ppp* | ipsec* | tun* | tap* | gpd* | wg*) return 0 ;; esac
  return 1
}

ROUTE=$(route -n get default 2>/dev/null) || unknown "route -n get default failed: no default route?"
IFACE=$(printf '%s\n' "$ROUTE" | awk '$1 == "interface:" { print $2; exit }')
[ -n "$IFACE" ] || unknown "the default route names no interface"

IFCONFIG=$(ifconfig -a 2>/dev/null) || unknown "ifconfig -a failed"
# each interface: its name, whether it is point-to-point, whether it holds an IPv4 address
TABLE=$(printf '%s\n' "$IFCONFIG" | awk '
  /^[^ \t]/ { if (name != "") print name, p2p, v4; name = $1; sub(/:$/, "", name); p2p = ($0 ~ /POINTOPOINT/) ? 1 : 0; v4 = 0; next }
  $1 == "inet" { v4 = 1 }
  END { if (name != "") print name, p2p, v4 }')
# the interface the default route names must be among them, or the answer cannot be trusted
printf '%s\n' "$TABLE" | awk -v want="$IFACE" '$1 == want { found = 1 } END { exit !found }' \
  || unknown "ifconfig does not list $IFACE, the default route's interface"

DEFAULT_P2P=$(printf '%s\n' "$TABLE" | awk -v want="$IFACE" '$1 == want { print $2; exit }')
if tunnel_name "$IFACE" || [ "$DEFAULT_P2P" = 1 ]; then
  echo "vpn: on $IFACE (the default route goes through it)"
  exit 1
fi
while read -r name p2p v4; do
  [ "$v4" = 1 ] || continue
  case "$name" in lo*) continue ;; esac
  if tunnel_name "$name" || [ "$p2p" = 1 ]; then
    echo "vpn: on $name (a tunnel holding an IPv4 address)"
    exit 1
  fi
done <<EOF
$TABLE
EOF
echo "vpn: off"
exit 0
