"""
Replay test for fixtures/05-six-hop-cdn-waf-gw-app-svc-db.

A 13-SG fleet whose core is a SIX-hop SG-reference chain: internet -> cdn -> waf -> gw ->
app -> svc -> db. Every rule accepts exactly one upstream tier and is textbook in
isolation; the depth is the point -- the full internet-to-database path spans six separate
security groups, with the billing-service settlement-writer as the last link. Surrounding
it are scoped tiers (bastion, monitoring, ci, ssm) and app-fed leaves (cache, queue, logs)
that pad the haystack and fan out from app (so app is also a bridging hub).

Stdlib only. Run with: `python tests/replay_05_six_hop_cdn_waf_gw_app_svc_db.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _deep import run_deep  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "05-six-hop-cdn-waf-gw-app-svc-db"


def main() -> int:
    r = run_deep(FIXTURE_DIR)
    p1 = next((f for f in r.findings if f.code == "P1"), None)

    assertions = [
        ("P1" in r.codes() and "B1" in r.codes(), f"expected P1 + B1, got {sorted(r.codes())}"),
        (r.top_severity == "critical", "a path to the crown jewel must be critical"),
        (r.shortest_path == ["internet", "cdn", "waf", "gw", "app", "svc", "db"],
         f"expected internet->cdn->waf->gw->app->svc->db, got {r.shortest_path}"),
        (p1 is not None and len(p1.path) - 1 == 6, "the needle is a 6-hop chain across seven SGs"),
        ("db" in r.reachable, f"the crown jewel must be in the blast radius, got {r.reachable}"),
        (r.sg_count >= 10, f"this is a high-volume fleet, got {r.sg_count} SGs"),
    ]
    return report("replay_05_six_hop_cdn_waf_gw_app_svc_db", r, assertions)


if __name__ == "__main__":
    sys.exit(main())
