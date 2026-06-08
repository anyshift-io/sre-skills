"""
Replay test for examples/10-multi-region-asymmetry.md.

Stdlib only. Run with: `python tests/replay_10_multi_region.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _methodology import run_investigation  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "10-multi-region-asymmetry"


def main() -> int:
    inv = run_investigation(
        fixture_dir=FIXTURE_DIR,
        t0_iso="2026-09-14T11:42:00Z",
        tnow_iso="2026-09-14T11:50:00Z",
    )

    assertions = [
        (len(inv.change_surface) == 0, f"expected 0 changes in window, got {len(inv.change_surface)}"),

        # Step 3: outside-reference-paths (no reference path for regional config drift).
        (inv.classified_path == "outside-reference-paths", f"expected outside-reference-paths, got {inv.classified_path}"),

        # Regional asymmetry detected by the detector.
        (inv.regional_asymmetry.get("detected") is True, f"expected regional_asymmetry.detected=True, got {inv.regional_asymmetry}"),
        ("us-east-1" in inv.regional_asymmetry.get("per_region_peak_error_rate_pct", {}), "expected per-region breakdown to include us-east-1"),
        ("us-west-2" in inv.regional_asymmetry.get("per_region_peak_error_rate_pct", {}), "expected per-region breakdown to include us-west-2"),

        # ESCALATE with M1 + regional-asymmetry.
        (inv.escalate_to_human is True, "must escalate per M1 + regional asymmetry"),
        (any("regional" in r.lower() for r in inv.escalation_reasons), f"expected regional-asymmetry escalation, got {inv.escalation_reasons}"),

        # Handoff payload carries the regional asymmetry data.
        (inv.handoff["regional_asymmetry"].get("detected") is True, "handoff must include regional_asymmetry"),
    ]

    failed = [msg for ok, msg in assertions if not ok]
    if failed:
        print("FAIL: replay_10_multi_region")
        for msg in failed:
            print(f"  - {msg}")
        return 1

    print(f"PASS: replay_10_multi_region ({len(assertions)} assertions)")
    print(f"  classified_path:    {inv.classified_path}")
    print(f"  regional_asymmetry: {inv.regional_asymmetry.get('per_region_peak_error_rate_pct')}")
    print(f"  escalate:           {inv.escalate_to_human} ({', '.join(inv.escalation_reasons)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
