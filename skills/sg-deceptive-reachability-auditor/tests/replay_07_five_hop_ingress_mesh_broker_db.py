"""
Replay test for fixtures/07-five-hop-ingress-mesh-broker-db.

A 12-SG fleet whose core is a FIVE-hop SG-reference chain: internet -> ingress -> mesh ->
app -> broker -> db. Each tier accepts exactly one upstream and is fine in isolation; the
chain only appears when all five hops are composed, with the event-broker journal-writer
as the offbeat last link into the database. The app-fed leaves (cache, queue, logs) and
scoped tiers (bastion, monitoring, ci, ssm) pad the haystack and fan out from app (so app
is also a bridging hub).

Stdlib only. Run with: `python tests/replay_07_five_hop_ingress_mesh_broker_db.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _deep import run_deep  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "07-five-hop-ingress-mesh-broker-db"


def main() -> int:
    r = run_deep(FIXTURE_DIR)
    p1 = next((f for f in r.findings if f.code == "P1"), None)

    assertions = [
        ("P1" in r.codes() and "B1" in r.codes(), f"expected P1 + B1, got {sorted(r.codes())}"),
        (r.top_severity == "critical", "a path to the crown jewel must be critical"),
        (r.shortest_path == ["internet", "ingress", "mesh", "app", "broker", "db"],
         f"expected internet->ingress->mesh->app->broker->db, got {r.shortest_path}"),
        (p1 is not None and len(p1.path) - 1 == 5, "the needle is a 5-hop chain across six SGs"),
        ("db" in r.reachable, f"the crown jewel must be in the blast radius, got {r.reachable}"),
        (r.sg_count >= 10, f"this is a high-volume fleet, got {r.sg_count} SGs"),
    ]
    return report("replay_07_five_hop_ingress_mesh_broker_db", r, assertions)


if __name__ == "__main__":
    sys.exit(main())
