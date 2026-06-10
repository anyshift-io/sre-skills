"""
Replay test for examples/05-default-visibility-short-retention.md.

Stdlib only. Run with: `python tests/replay_05_default_visibility.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "05-default-visibility-short-retention"


def main() -> int:
    audit = run_audit(FIXTURE_DIR, is_processing_queue=True)

    assertions = [
        # Two soft flags fire together: R5 (default 30s visibility) and R6 (300s retention).
        ("R5" in audit.codes(), f"expected R5 (default visibility), got {sorted(audit.codes())}"),
        ("R6" in audit.codes(), f"expected R6 (short retention), got {sorted(audit.codes())}"),
        (audit.codes() == {"R5", "R6"}, f"expected exactly {{R5, R6}}, got {sorted(audit.codes())}"),

        # Neither is critical: these are flags to verify, not confirmed message-loss bugs.
        # 30s * 5 = 150s < 300s retention so R4 must NOT fire.
        (audit.top_severity == "medium", f"top severity should be medium (R6), got {audit.top_severity}"),
        (all(f.severity != "critical" for f in audit.findings), "no critical findings expected here"),

        # R5 must honestly defer to the consumer-processing-time boundary, not assert a bug.
        (next(f.severity for f in audit.findings if f.code == "R5") == "low", "R5 is a low-severity risk flag"),
        (any("processing time" in b.lower() or "consumer" in b.lower() for b in audit.boundary),
         "boundary must name the consumer-processing-time join R5 depends on"),
    ]

    return report("replay_05_default_visibility", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())
