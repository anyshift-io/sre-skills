"""
Replay test for examples/08-service-wildcard-exfil.md.

Two wildcards that co-occur: a sensitive-service wildcard and a broad read reach.

Stdlib only. Run with: `python tests/replay_08_service_wildcard_exfil.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "08-service-wildcard-exfil"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)
    w2 = next((f for f in audit.findings if f.code == "W2"), None)
    w5 = next((f for f in audit.findings if f.code == "W5"), None)

    assertions = [
        (audit.codes() == {"W2", "W5"}, f"expected {{W2, W5}}, got {sorted(audit.codes())}"),

        # W2: secretsmanager:* is the high finding; W5: broad s3 read is the low one.
        (w2 is not None and w2.severity == "high", "W2 (secretsmanager:*) must be high"),
        (w5 is not None and w5.severity == "low", "W5 (broad read reach) must be low"),
        (audit.top_severity == "high", f"top severity should be high, got {audit.top_severity}"),

        # W2 expands the service wildcard to a concrete sensitive permission.
        ("FullSecretsAccess" in audit.expanded, "the secretsmanager:* statement should be expanded"),
        ("secretsmanager:GetSecretValue" in audit.expanded.get("FullSecretsAccess", []), "expansion should surface GetSecretValue"),

        # W5 is honest: a data-classification reach, deferred to the boundary, not a confirmed leak.
        (w5 is not None and ("classification" in w5.detail.lower() or "verify" in w5.detail.lower()), "W5 should present itself as a reach to verify, not a confirmed leak"),
    ]

    return report("replay_08_service_wildcard_exfil", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())
