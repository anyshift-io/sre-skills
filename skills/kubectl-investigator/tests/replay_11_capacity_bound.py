"""
Replay test for examples/11-capacity-bound-organic-growth.md.

Stdlib only. Run with: `python tests/replay_11_capacity_bound.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _methodology import run_investigation  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "11-capacity-bound-organic-growth"


def main() -> int:
    inv = run_investigation(
        fixture_dir=FIXTURE_DIR,
        t0_iso="2026-10-08T10:55:00Z",
        tnow_iso="2026-10-08T11:05:00Z",
    )

    assertions = [
        (len(inv.change_surface) == 0, f"expected 0 changes in window, got {len(inv.change_surface)}"),

        # Step 3: outside-reference-paths (no reference path for capacity saturation).
        (inv.classified_path == "outside-reference-paths", f"expected outside-reference-paths, got {inv.classified_path}"),

        # Step 5: request rate growth detected (>=1.5x baseline across window).
        (inv.blast_radius.get("request_rate_growing") is True, f"expected request_rate_growing=True, got {inv.blast_radius.get('request_rate_growing')}"),

        # Step 6: scale_resource is in the recommendation list (the key behavior for this scenario).
        (any(m["action"] == "scale_resource" for m in inv.mitigation_ranked), f"expected scale_resource in mitigations, got {[m['action'] for m in inv.mitigation_ranked]}"),

        # No revert recommendation (no change to revert).
        (not any(m["action"] == "revert" for m in inv.mitigation_ranked), "must not recommend revert with zero changes"),

        # Step 7: ESCALATE per M1.
        (inv.escalate_to_human is True, "must escalate per M1"),
        (any("M1" in r for r in inv.escalation_reasons), f"expected M1, got {inv.escalation_reasons}"),
    ]

    failed = [msg for ok, msg in assertions if not ok]
    if failed:
        print("FAIL: replay_11_capacity_bound")
        for msg in failed:
            print(f"  - {msg}")
        return 1

    print(f"PASS: replay_11_capacity_bound ({len(assertions)} assertions)")
    print(f"  classified_path:       {inv.classified_path}")
    print(f"  request_rate_growing:  {inv.blast_radius.get('request_rate_growing')}")
    print(f"  recommended actions:   {', '.join(m['action'] for m in inv.mitigation_ranked)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
