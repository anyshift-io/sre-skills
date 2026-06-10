"""
Replay test for examples/04-update-function-code.md.

Overwrite the code of a function that already runs with a privileged role.

Stdlib only. Run with: `python tests/replay_04_update_function_code.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "04-update-function-code"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)
    e3 = next((f for f in audit.findings if f.code == "E3"), None)

    assertions = [
        (e3 is not None, f"expected E3 (hijack Lambda role), got {sorted(audit.codes())}"),
        (e3 is not None and e3.severity == "critical", "E3 must be critical"),
        (audit.codes() == {"E3"}, f"UpdateFunctionCode is scoped to a function ARN (no W4); expected just {{E3}}, got {sorted(audit.codes())}"),

        (e3 is not None and "UpdateFunctionCode" in e3.attribute, "E3 should name lambda:UpdateFunctionCode"),
        # This fixture also grants PassRole, so the detail should note the self-contained variant.
        (e3 is not None and "PassRole" in e3.detail, "E3 detail should mention the PassRole that makes it end-to-end here"),
    ]

    return report("replay_04_update_function_code", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())
