"""
Replay test for examples/09-zero-changes-external-cert-expiry.md.

Stdlib only. Run with: `python tests/replay_09_cert_expiry.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _methodology import run_investigation  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "09-zero-changes-external-cert-expiry"


def main() -> int:
    inv = run_investigation(
        fixture_dir=FIXTURE_DIR,
        t0_iso="2026-08-20T03:18:00Z",
        tnow_iso="2026-08-20T03:25:00Z",
    )

    assertions = [
        # Step 2: zero changes in window (this is the key signal for this scenario).
        (len(inv.change_surface) == 0, f"expected 0 changes in window, got {len(inv.change_surface)}"),

        # Step 3: outside-reference-paths (no internal classification fits).
        (inv.classified_path == "outside-reference-paths", f"expected outside-reference-paths, got {inv.classified_path}"),

        # Should NOT be classified as DNS just because there are TLS errors on outbound calls.
        # (TLS != DNS: the resolver works, the handshake fails.)
        (inv.classified_path != "DNS", "must distinguish TLS handshake failure from DNS resolution failure"),

        # Step 6: no revert (no change in window).
        (not any(m["action"] == "revert" for m in inv.mitigation_ranked), "must not recommend revert with zero changes"),

        # Step 7: ESCALATE per M1.
        (inv.escalate_to_human is True, "must escalate per M1"),
        (any("M1" in r for r in inv.escalation_reasons), f"expected M1, got {inv.escalation_reasons}"),
    ]

    failed = [msg for ok, msg in assertions if not ok]
    if failed:
        print("FAIL: replay_09_cert_expiry")
        for msg in failed:
            print(f"  - {msg}")
        return 1

    print(f"PASS: replay_09_cert_expiry ({len(assertions)} assertions)")
    print(f"  classified_path: {inv.classified_path}")
    print(f"  escalate:        {inv.escalate_to_human}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
