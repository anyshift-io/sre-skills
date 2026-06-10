"""
Replay test for examples/01-no-dlq.md.

Stdlib only. Run with: `python tests/replay_01_no_dlq.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "01-no-dlq"


def main() -> int:
    audit = run_audit(FIXTURE_DIR, is_processing_queue=True)

    assertions = [
        (audit.queue_arn.endswith(":payments-capture"), f"unexpected queue arn {audit.queue_arn}"),
        (audit.has_dlq is False, "queue has no RedrivePolicy, has_dlq should be False"),

        # R1 is the finding: no DLQ on a processing queue.
        ("R1" in audit.codes(), f"expected R1 (no DLQ), got {sorted(audit.codes())}"),
        (next(f.severity for f in audit.findings if f.code == "R1") == "high", "R1 should be high severity"),

        # The queue sets a deliberate visibility timeout (120) and the default retention,
        # so R5 / R6 must NOT fire: R1 is the only finding.
        (audit.codes() == {"R1"}, f"expected exactly {{R1}}, got {sorted(audit.codes())}"),

        # The wall is always named.
        (any("consumer" in b.lower() for b in audit.boundary), "boundary must name the consumer join"),
        (len(audit.boundary) >= 4, f"expected >=4 boundary notes, got {len(audit.boundary)}"),
    ]

    return report("replay_01_no_dlq", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())
