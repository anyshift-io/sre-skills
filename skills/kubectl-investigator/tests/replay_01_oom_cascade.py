"""
Replay test for examples/01-oom-cascade.md.

Runs the reference methodology in `_methodology.py` against the OOM cascade
fixtures and asserts the methodology produces the expected classification,
mitigation, and handoff payload.

Stdlib only. Run with: `python tests/replay_01_oom_cascade.py`.
Exits 0 on success, 1 on any assertion failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _methodology import run_investigation  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "01-oom-cascade"


def main() -> int:
    inv = run_investigation(
        fixture_dir=FIXTURE_DIR,
        t0_iso="2026-03-12T14:32:00Z",
        tnow_iso="2026-03-12T14:36:00Z",
        failing_surface_hints=["webhook", "buffer"],
    )

    assertions = [
        # Step 1: window anchored correctly with the 15-minute lead-in.
        (inv.window[0].isoformat() == "2026-03-12T14:17:00+00:00", f"window start expected 14:17:00Z, got {inv.window[0].isoformat()}"),

        # Step 2: change surface contains the 14:18 deploy and nothing else.
        (len(inv.change_surface) == 1, f"expected 1 change in window, got {len(inv.change_surface)}"),
        (inv.change_surface[0]["kind"] == "deploy", f"expected deploy, got {inv.change_surface[0]['kind']}"),
        (inv.change_surface[0]["version"] == "v4.18.0", f"expected v4.18.0, got {inv.change_surface[0]['version']}"),

        # Step 3: classified as OOM (not cascading-failure, not deploy-correlator).
        (inv.classified_path == "OOM", f"expected OOM, got {inv.classified_path}"),
        (any("OOMKilled" in e for e in inv.classification_evidence), "expected OOMKilled in classification evidence"),
        (any("webhook" in e.lower() or "buffer" in e.lower() for e in inv.classification_evidence), "expected webhook/buffer surface match in evidence"),

        # Step 4: at least three independent signal sources.
        (len({s["source"] for s in inv.confirming_signals}) >= 3, f"expected >=3 independent signal sources, got {len({s['source'] for s in inv.confirming_signals})}"),

        # Step 5: blast radius reflects payment-traffic failure (>10% error rate at peak).
        (inv.blast_radius["error_rate_peak_pct"] >= 10, f"expected error_rate_peak_pct >= 10, got {inv.blast_radius['error_rate_peak_pct']}"),

        # Step 6: mitigation ranked, revert first.
        (inv.mitigation_ranked[0]["action"] == "revert", f"expected revert as first mitigation, got {inv.mitigation_ranked[0]['action']}"),
        (any("scale_resource" == m["action"] for m in inv.mitigation_ranked), "expected scale_resource as a fallback mitigation"),

        # Step 7: handoff payload includes the right classified path and is not escalated.
        (inv.handoff["classified_path"] == "OOM", "handoff payload should carry OOM classification"),
        (inv.escalate_to_human is False, f"OOM-with-3-signals should not escalate, got escalation_reasons={inv.escalation_reasons}"),
    ]

    failed = [msg for ok, msg in assertions if not ok]
    if failed:
        print("FAIL: replay_01_oom_cascade")
        for msg in failed:
            print(f"  - {msg}")
        return 1

    print(f"PASS: replay_01_oom_cascade ({len(assertions)} assertions)")
    print(f"  classified_path: {inv.classified_path}")
    print(f"  recommended:     {inv.mitigation_ranked[0]['action']} -> {inv.mitigation_ranked[0]['target']}")
    print(f"  signals:         {len(inv.confirming_signals)} from {len({s['source'] for s in inv.confirming_signals})} sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
