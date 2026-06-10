"""
Replay test for examples/07-fifo-dedup-off.md.

Stdlib only. Run with: `python tests/replay_07_fifo_dedup_off.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "07-fifo-dedup-off"


def main() -> int:
    audit = run_audit(FIXTURE_DIR, is_processing_queue=True)
    r9 = next((f for f in audit.findings if f.code == "R9"), None)

    assertions = [
        (audit.is_fifo is True, "queue ends in .fifo, is_fifo should be True"),

        # R9: FIFO with content-based dedup off depends on producers sending dedup IDs.
        (r9 is not None, f"expected R9 (FIFO dedup contract), got {sorted(audit.codes())}"),
        (r9 is not None and r9.severity == "low", "R9 is a low-severity contract flag"),
        (audit.codes() == {"R9"}, f"expected exactly {{R9}}, got {sorted(audit.codes())}"),

        # The finding must defer the actual verification to the producer side (the wall).
        (r9 is not None and "producer" in r9.detail.lower(), "R9 detail must name the producer dependency"),
        (any("producer" in b.lower() for b in audit.boundary), "boundary must name the producer join"),
    ]

    return report("replay_07_fifo_dedup_off", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())
