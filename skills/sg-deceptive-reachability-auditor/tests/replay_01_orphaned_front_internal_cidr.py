"""
Replay test for fixtures/01-orphaned-front-internal-cidr.

A clean control with full fleet volume (11 SGs) and a DECEPTIVE deep chain. The config
shows a long SG-reference chain web -> app -> session cache -> db, which looks like a
buried lateral path. But the web frontend accepts only the internal service-mesh CIDR,
NOT the public ALB SG, so that chain is orphaned from the internet entry: the internet
reaches only the directly-exposed public ALB and stops. The database is NOT reachable.
The audit must report no path, must NOT mistake the visible-but-disconnected chain for a
reachable one, and must still name the boundary.

Stdlib only. Run with: `python tests/replay_01_orphaned_front_internal_cidr.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _deep import run_deep  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "01-orphaned-front-internal-cidr"


def main() -> int:
    r = run_deep(FIXTURE_DIR)

    assertions = [
        (r.clean, f"expected a clean audit, got {sorted(r.codes())}"),
        (r.top_severity is None, "a clean audit has no top severity"),
        (r.shortest_path == [], f"no path to the crown jewel should exist, got {r.shortest_path}"),
        ("db" not in r.reachable, f"the database must NOT be in the blast radius, got {r.reachable}"),
        # Only the directly-exposed public ALB is reachable; the deep chain is orphaned.
        (set(r.reachable) == {"lb"}, f"only the public ALB tier is reachable, got {r.reachable}"),
        (r.sg_count >= 10, f"this is a high-volume fleet, got {r.sg_count} SGs"),
        (len(r.boundary) >= 3, "even a clean graph reports the joins it cannot make"),
    ]
    return report("replay_01_orphaned_front_internal_cidr", r, assertions)


if __name__ == "__main__":
    sys.exit(main())
