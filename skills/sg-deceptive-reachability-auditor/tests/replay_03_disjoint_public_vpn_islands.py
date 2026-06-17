"""
Replay test for fixtures/03-disjoint-public-vpn-islands.

A clean control with full fleet volume (11 SGs) and a DECEPTIVE two-island layout. One
island is internet-facing (public ALB -> web -> web-app, wired by CIDR, not SG refs, and
a dead end). The other is a data island wired with a juicy-looking deep SG-ref chain
admin plane -> data processor -> db (+ analytics cache), but the admin plane accepts only
the corp VPN CIDR and has no inbound SG reference, so the data island is reachable only
from the VPN, never from the internet. No edge joins the two islands. The crown-jewel
database is NOT reachable from the internet entry. The audit must report no path and must
NOT splice the two islands into a manufactured internet -> db route.

Stdlib only. Run with: `python tests/replay_03_disjoint_public_vpn_islands.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _deep import run_deep  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "03-disjoint-public-vpn-islands"


def main() -> int:
    r = run_deep(FIXTURE_DIR)

    assertions = [
        (r.clean, f"expected a clean audit, got {sorted(r.codes())}"),
        (r.top_severity is None, "a clean audit has no top severity"),
        (r.shortest_path == [], f"no path to the crown jewel should exist, got {r.shortest_path}"),
        ("db" not in r.reachable, f"the database must NOT be in the blast radius, got {r.reachable}"),
        # The data island (admin/dataproc/db/cache) must NOT be reachable from the internet.
        (set(r.reachable) == {"lb"}, f"only the public ALB tier is reachable, got {r.reachable}"),
        (r.sg_count >= 10, f"this is a high-volume fleet, got {r.sg_count} SGs"),
        (len(r.boundary) >= 3, "even a clean graph reports the joins it cannot make"),
    ]
    return report("replay_03_disjoint_public_vpn_islands", r, assertions)


if __name__ == "__main__":
    sys.exit(main())
