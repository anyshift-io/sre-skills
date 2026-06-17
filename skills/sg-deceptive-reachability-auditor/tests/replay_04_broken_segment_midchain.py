"""
Replay test for fixtures/04-broken-segment-midchain.

A clean control with full fleet volume (10 SGs) and a DECEPTIVE broken chain. A long
service chain is visible (public edge proxy -> web -> app -> session cache -> db), and the
edge proxy carries the only 0.0.0.0/0 ingress. But the chain is cut at the first internal
hop: the web frontend accepts only the internal mesh CIDR, NOT the edge proxy SG, so the
edge -> web link is not an SG edge and the rest of the chain is orphaned. The internet
reaches only the directly-exposed edge proxy and stops. The database is NOT reachable. The
audit must report no path, must NOT mistake the visible-but-broken chain for a reachable
one, and must still name the boundary.

Stdlib only. Run with: `python tests/replay_04_broken_segment_midchain.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _deep import run_deep  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "04-broken-segment-midchain"


def main() -> int:
    r = run_deep(FIXTURE_DIR)

    assertions = [
        (r.clean, f"expected a clean audit, got {sorted(r.codes())}"),
        (r.top_severity is None, "a clean audit has no top severity"),
        (r.shortest_path == [], f"no path to the crown jewel should exist, got {r.shortest_path}"),
        ("db" not in r.reachable, f"the database must NOT be in the blast radius, got {r.reachable}"),
        # Only the directly-exposed public edge proxy is reachable; the chain is cut after it.
        (set(r.reachable) == {"edge"}, f"only the public edge proxy tier is reachable, got {r.reachable}"),
        (r.sg_count >= 10, f"this is a high-volume fleet, got {r.sg_count} SGs"),
        (len(r.boundary) >= 3, "even a clean graph reports the joins it cannot make"),
    ]
    return report("replay_04_broken_segment_midchain", r, assertions)


if __name__ == "__main__":
    sys.exit(main())
