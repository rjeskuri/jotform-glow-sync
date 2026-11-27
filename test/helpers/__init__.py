"""
The tests' shared helpers (test/helpers/*.py). Importing any of them - or `import helpers` alone -
stands in for the VPN check (ticket #251): glow.salesforce.require_vpn_off runs the check
glow.salesforce.VPN_CHECK names (its argv, read at each call; by default scripts/vpn_check.sh, which
reads route and ifconfig) beside --vpn-off, and no test may run the real one - CI is a Linux
container, and on the Mac it would read the network. VPN_OFF says the VPN is off. A test of the check
itself sets its own (test/salesforce_test.py: ToolCommandLines, VpnCheck).
"""
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from glow import salesforce as _salesforce  # noqa: E402

VPN_OFF = ["/bin/sh", "-c", "echo 'vpn: off'"]
_salesforce.VPN_CHECK = VPN_OFF
