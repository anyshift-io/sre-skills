"""
Replay test for examples/06-ambiguous-t0-slow-burn.md.

Stdlib only. Run with: `python tests/replay_06_ambiguous_t0.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _methodology import run_investigation  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "06-ambiguous-t0-slow-burn"


def main() -> int:
    inv = run_investigation(
        fixture_dir=FIXTURE_DIR,
        t0_iso="2026-04-19T09:32:14Z",
        tnow_iso="2026-04-19T12:15:00Z",
        t0_ambiguous=True,
    )

    assertions = [
        # Step 1: window spans ~3 hours (T0 + 15min lead-in).
        ((inv.tnow - inv.window[0]).total_seconds() >= 9000, f"expected widened window >=150min, got {(inv.tnow - inv.window[0]).total_seconds() / 60:.0f}min"),

        # Step 2: zero changes in window (the actual causal deploy is 3 days outside).
        (len(inv.change_surface) == 0, f"expected 0 changes in window, got {len(inv.change_surface)}"),

        # Step 3: OOM classification on signature (slow trajectory).
        (inv.classified_path == "OOM", f"expected OOM (slow), got {inv.classified_path}"),

        # Step 7: t0_ambiguous propagated, escalation triggered with M2.
        (inv.t0_ambiguous is True, "expected t0_ambiguous=True on Investigation"),
        (inv.escalate_to_human is True, "expected escalation when T0 is ambiguous"),
        (any("M2" in r for r in inv.escalation_reasons), f"expected M2 escalation reason, got {inv.escalation_reasons}"),

        # Handoff payload carries t0_ambiguous flag.
        (inv.handoff["t0_ambiguous"] is True, "handoff must carry t0_ambiguous=True"),
        (inv.handoff["escalate_to_human"] is True, "handoff must carry escalate_to_human=True"),
    ]

    failed = [msg for ok, msg in assertions if not ok]
    if failed:
        print("FAIL: replay_06_ambiguous_t0")
        for msg in failed:
            print(f"  - {msg}")
        return 1

    print(f"PASS: replay_06_ambiguous_t0 ({len(assertions)} assertions)")
    print(f"  classified_path: {inv.classified_path}")
    print(f"  t0_ambiguous:    {inv.t0_ambiguous}")
    print(f"  escalate:        {inv.escalate_to_human} ({', '.join(inv.escalation_reasons)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
