"""
Replay test for examples/03-maxreceivecount-too-low.md.

Stdlib only. Run with: `python tests/replay_03_maxreceivecount.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "03-maxreceivecount-too-low"


def main() -> int:
    audit = run_audit(FIXTURE_DIR, is_processing_queue=True)
    r2 = next((f for f in audit.findings if f.code == "R2"), None)

    assertions = [
        (audit.has_dlq is True, "queue has a DLQ, has_dlq should be True"),

        # R2 fires for maxReceiveCount=1: transient failures dead-letter good messages.
        (r2 is not None, f"expected R2 (maxReceiveCount band), got {sorted(audit.codes())}"),
        (r2 is not None and r2.severity == "medium", "R2-low should be medium severity"),
        (r2 is not None and "1" in r2.title, "R2 title should name the offending maxReceiveCount"),

        # DLQ retention (14d) > source (4d) so no R3; 1*60 << retention so no R4.
        (audit.codes() == {"R2"}, f"expected exactly {{R2}}, got {sorted(audit.codes())}"),
    ]

    return report("replay_03_maxreceivecount", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())
