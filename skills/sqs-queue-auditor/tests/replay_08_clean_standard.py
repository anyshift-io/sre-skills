"""
Replay test for examples/08-clean-standard.md.

The control case: a correctly-configured queue must produce zero findings. This
guards against false positives, which are how an auditor loses an operator's trust.

Stdlib only. Run with: `python tests/replay_08_clean_standard.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "08-clean-standard"


def main() -> int:
    audit = run_audit(FIXTURE_DIR, is_processing_queue=True)

    assertions = [
        (audit.has_dlq is True, "queue has a well-sized DLQ"),

        # Zero findings: deliberate visibility (180s), default retention, DLQ at 14d,
        # maxReceiveCount 5, SSE on, and a resource policy scoped by aws:SourceArn.
        (audit.clean is True, f"clean queue should produce no findings, got {sorted(audit.codes())}"),
        (audit.top_severity is None, f"clean queue should have no top severity, got {audit.top_severity}"),

        # The wildcard-principal policy here is narrowed by aws:SourceArn, so R7 must NOT fire.
        ("R7" not in audit.codes(), "an aws:SourceArn-conditioned policy must not trip R7"),

        # Even a clean queue still reports the boundary: a clean config is not a clean system.
        (len(audit.boundary) >= 4, f"expected >=4 boundary notes even when clean, got {len(audit.boundary)}"),
    ]

    return report("replay_08_clean_standard", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())
