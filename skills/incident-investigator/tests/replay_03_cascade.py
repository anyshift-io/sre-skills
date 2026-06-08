"""
Replay test for examples/03-cascading-failure-retry-storm.md.

Stdlib only. Run with: `python tests/replay_03_cascade.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _methodology import run_investigation  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "03-cascading-failure-retry-storm"


def main() -> int:
    inv = run_investigation(
        fixture_dir=FIXTURE_DIR,
        t0_iso="2026-03-20T11:08:00Z",
        tnow_iso="2026-03-20T11:15:00Z",
    )

    assertions = [
        (inv.window[0].isoformat() == "2026-03-20T10:53:00+00:00", f"window start expected 10:53:00Z, got {inv.window[0].isoformat()}"),

        # Step 2: zero changes in window.
        (len(inv.change_surface) == 0, f"expected 0 changes in window, got {len(inv.change_surface)}"),

        # Step 3: cascading-failure classification, triggered by upstream latency growth.
        (inv.classified_path == "cascading-failure", f"expected cascading-failure, got {inv.classified_path}"),
        (any("upstream" in e.lower() or "retry rate" in e.lower() for e in inv.classification_evidence), f"expected upstream-latency or retry-rate evidence, got {inv.classification_evidence}"),

        # Step 4: at least 3 independent signal sources (no change_audit possible since no changes).
        (len({s["source"] for s in inv.confirming_signals}) >= 3, f"expected >=3 independent signal sources, got {len({s['source'] for s in inv.confirming_signals})}"),

        # Step 5: blast radius reflects partial failure with high gateway retry pressure.
        (5 <= inv.blast_radius["error_rate_peak_pct"] <= 20, f"expected partial error rate (5-20%), got {inv.blast_radius['error_rate_peak_pct']}"),

        # Step 6: mitigation should NOT lead with revert (no change in window); circuit-breaker first.
        (inv.mitigation_ranked[0]["action"] == "circuit_breaker", f"expected circuit_breaker as first mitigation, got {inv.mitigation_ranked[0]['action']}"),
        (any(m["action"] == "traffic_shift" for m in inv.mitigation_ranked), "expected traffic_shift as a follow-up mitigation"),
        (not any(m["action"] == "revert" for m in inv.mitigation_ranked), "should NOT recommend revert when no change in window"),

        # Step 7: handoff payload reflects the classification, no escalation needed (3 signals confirmed).
        (inv.handoff["classified_path"] == "cascading-failure", "handoff payload should carry cascading-failure classification"),
        (inv.escalate_to_human is False, f"cascade-with-3-signals should not escalate, got escalation_reasons={inv.escalation_reasons}"),
    ]

    failed = [msg for ok, msg in assertions if not ok]
    if failed:
        print("FAIL: replay_03_cascade")
        for msg in failed:
            print(f"  - {msg}")
        return 1

    print(f"PASS: replay_03_cascade ({len(assertions)} assertions)")
    print(f"  classified_path: {inv.classified_path}")
    print(f"  recommended:     {inv.mitigation_ranked[0]['action']} -> {inv.mitigation_ranked[0]['target']}")
    print(f"  signals:         {len(inv.confirming_signals)} from {len({s['source'] for s in inv.confirming_signals})} sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
