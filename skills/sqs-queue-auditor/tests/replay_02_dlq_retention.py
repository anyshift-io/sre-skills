"""
Replay test for examples/02-dlq-retention-shorter-than-source.md.

Stdlib only. Run with: `python tests/replay_02_dlq_retention.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "02-dlq-retention-shorter-than-source"


def main() -> int:
    audit = run_audit(FIXTURE_DIR, is_processing_queue=True)
    r3 = next((f for f in audit.findings if f.code == "R3"), None)

    assertions = [
        (audit.has_dlq is True, "queue has a RedrivePolicy, has_dlq should be True"),

        # R3 is the critical finding: DLQ retention (1d) <= source retention (4d).
        (r3 is not None, f"expected R3 (DLQ retention ordering), got {sorted(audit.codes())}"),
        (r3 is not None and r3.severity == "critical", "R3 must be critical"),
        (audit.top_severity == "critical", f"top severity should be critical, got {audit.top_severity}"),

        # maxReceiveCount (5) is in band and 5*60 << retention, so R2 / R4 must NOT fire.
        (audit.codes() == {"R3"}, f"expected exactly {{R3}}, got {sorted(audit.codes())}"),

        # The detail must call out the non-resetting SentTimestamp, the crux of the bug.
        (r3 is not None and "senttimestamp" in r3.detail.lower(), "R3 detail must explain the non-resetting SentTimestamp"),
    ]

    return report("replay_02_dlq_retention", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())
