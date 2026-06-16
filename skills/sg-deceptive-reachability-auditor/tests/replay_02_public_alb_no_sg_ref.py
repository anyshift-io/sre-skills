"""
Replay test for fixtures/02-public-alb-no-sg-ref.

A clean control with full fleet volume (11 SGs) and a loud-looking surface. A public ALB
carries the only 0.0.0.0/0 (and ::/0) ingress on 443/80 -- the intended public entry. A
deep service chain web -> app -> internal services -> db is wired with SG references
downstream, but NOTHING references the public ALB SG (it forwards to its target group by
registered IP), so no SG-to-SG edge composes from the internet into the fleet. The
database is NOT reachable. The audit must report no path, must NOT headline the intended
public ALB as a lateral chain, and must still name the boundary.

Stdlib only. Run with: `python tests/replay_02_public_alb_no_sg_ref.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _deep import run_deep  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "02-public-alb-no-sg-ref"


def main() -> int:
    r = run_deep(FIXTURE_DIR)

    assertions = [
        (r.clean, f"expected a clean audit, got {sorted(r.codes())}"),
        (r.top_severity is None, "a clean audit has no top severity"),
        (r.shortest_path == [], f"no path to the crown jewel should exist, got {r.shortest_path}"),
        ("db" not in r.reachable, f"the database must NOT be in the blast radius, got {r.reachable}"),
        # Only the directly-exposed public ALB is reachable; no SG-ref composes onward.
        (set(r.reachable) == {"lb"}, f"only the public ALB tier is reachable, got {r.reachable}"),
        (r.sg_count >= 10, f"this is a high-volume fleet, got {r.sg_count} SGs"),
        (len(r.boundary) >= 3, "even a clean graph reports the joins it cannot make"),
    ]
    return report("replay_02_public_alb_no_sg_ref", r, assertions)


if __name__ == "__main__":
    sys.exit(main())
