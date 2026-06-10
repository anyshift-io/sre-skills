"""
Replay test for examples/04-poison-ages-out-before-dlq.md.

Stdlib only. Run with: `python tests/replay_04_poison_ages_out.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "04-poison-ages-out-before-dlq"


def main() -> int:
    audit = run_audit(FIXTURE_DIR, is_processing_queue=True)
    r4 = next((f for f in audit.findings if f.code == "R4"), None)

    assertions = [
        (audit.has_dlq is True, "queue has a DLQ wired, has_dlq should be True"),

        # R4 is the flagship critical finding: 1000 * 900s = 900000s > 345600s retention,
        # so poison messages age out before they ever reach the (correctly-wired) DLQ.
        (r4 is not None, f"expected R4 (poison ages out), got {sorted(audit.codes())}"),
        (r4 is not None and r4.severity == "critical", "R4 must be critical"),
        (r4 is not None and "900000" in r4.detail, "R4 detail must show the worst-case 900000s figure"),
        (audit.top_severity == "critical", f"top severity should be critical, got {audit.top_severity}"),

        # maxReceiveCount=1000 also trips R2-high (low). DLQ retention (14d) > source so no R3.
        ("R2" in audit.codes(), "maxReceiveCount=1000 should also raise R2-high"),
        (audit.codes() == {"R4", "R2"}, f"expected exactly {{R4, R2}}, got {sorted(audit.codes())}"),
    ]

    return report("replay_04_poison_ages_out", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())
