"""
Replay test for examples/10-scoped-passrole-boundary.md.

The honesty case: the same PassRole + RunInstances combo, but scoped. The skill
downgrades to high and defers the real question to the boundary instead of crying critical.

Stdlib only. Run with: `python tests/replay_10_scoped_passrole_boundary.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "10-scoped-passrole-boundary"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)
    e1 = next((f for f in audit.findings if f.code == "E1"), None)

    assertions = [
        (e1 is not None, f"expected E1 (PassRole + compute), got {sorted(audit.codes())}"),
        (audit.codes() == {"E1"}, f"expected exactly {{E1}}, got {sorted(audit.codes())}"),

        # PassRole is scoped to ONE role ARN: high, not critical. The escalation now depends
        # on what that role can do, which is behind the boundary.
        (e1 is not None and e1.severity == "high", "scoped PassRole must downgrade E1 from critical to high"),
        (e1 is not None and "batch-worker" in e1.detail, "E1 detail should name the scoped role the escalation depends on"),
        (e1 is not None and "boundary" in e1.detail.lower(), "E1 detail should defer the real question to the boundary"),

        # A permissions boundary IS provided here, so the audit must not claim 'no boundary'.
        (not any("No boundary document was provided" in b for b in audit.boundary), "boundary note must not claim a missing boundary when boundary.json is present"),
    ]

    return report("replay_10_scoped_passrole_boundary", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())
