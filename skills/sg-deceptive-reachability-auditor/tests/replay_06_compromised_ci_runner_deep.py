"""
Replay test for fixtures/06-compromised-ci-runner-deep.

A 12-SG fleet where the entry point is a COMPROMISED CI runner host (instance i-06ci0001),
not the internet. From that foothold a five-hop internal build-pipeline chain composes:
ci -> build -> artifact -> deploy -> app -> db. A separate public ALB -> web -> web-cache
front door exists but never touches the data plane, so the only path to the crown jewel is
the internal pipeline chain. The depth + non-internet entry is the point: the chain only
appears when the SG-to-SG hops are composed from the compromised host outward.

Stdlib only. Run with: `python tests/replay_06_compromised_ci_runner_deep.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _deep import run_deep  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "06-compromised-ci-runner-deep"


def main() -> int:
    r = run_deep(FIXTURE_DIR)
    p1 = next((f for f in r.findings if f.code == "P1"), None)

    assertions = [
        ("P1" in r.codes() and "B1" in r.codes(), f"expected P1 + B1, got {sorted(r.codes())}"),
        (r.top_severity == "critical", "a path to the crown jewel must be critical"),
        (r.shortest_path == ["ci", "build", "artifact", "deploy", "app", "db"],
         f"expected ci->build->artifact->deploy->app->db, got {r.shortest_path}"),
        (p1 is not None and len(p1.path) - 1 == 5, "the needle is a 5-hop chain from the compromised CI runner"),
        ("db" in r.reachable, f"the crown jewel must be in the blast radius, got {r.reachable}"),
        # The public web/cache island must NOT be reachable from the CI-runner entry.
        ("web" not in r.reachable and "cache" not in r.reachable,
         f"the public front door is a separate island, got {r.reachable}"),
        (r.sg_count >= 10, f"this is a high-volume fleet, got {r.sg_count} SGs"),
    ]
    return report("replay_06_compromised_ci_runner_deep", r, assertions)


if __name__ == "__main__":
    sys.exit(main())
