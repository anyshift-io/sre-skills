"""
Replay test for examples/11-clean-least-privilege.md.

The control. A least-privilege policy produces zero findings and still reports its boundary.

Stdlib only. Run with: `python tests/replay_11_clean_least_privilege.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "11-clean-least-privilege"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)

    assertions = [
        # No false positives: scoped reads/writes with conditions are not findings.
        (audit.clean, f"expected a clean audit, got {sorted(audit.codes())}"),
        (audit.top_severity is None, "a clean audit has no top severity"),

        # A clean config is not a clean system: the boundary is still reported.
        (len(audit.boundary) >= 3, "even a clean policy reports the joins it cannot make"),
        (any("permissions boundary" in b for b in audit.boundary), "boundary should name the permissions-boundary join"),
        (any("union" in b for b in audit.boundary), "boundary should name the other-attached-policies (union) join"),
        (any("SCP" in b or "Service Control Policy" in b for b in audit.boundary), "boundary should name the org SCP join"),
    ]

    return report("replay_11_clean_least_privilege", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())
