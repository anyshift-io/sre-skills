"""
Replay test for fixtures/03-saas-tenancy-clean.

Deceptive-clean estate: a 9-bucket multi-tenant SaaS estate. Several tenant-shared
buckets use Principal '*' narrowed by org id / external id, and one public ACL is
ignored by BPA. NO live exposure. Guards against reading Principal '*' and stopping.

Stdlib only. Run with: `python tests/replay_03_saas_tenancy_clean.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _estate import run_estate  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "03-saas-tenancy-clean"


def main() -> int:
    e = run_estate(FIXTURE_DIR)
    assertions = [
        (e.clean, f"estate must be CLEAN, got live codes {sorted(e.codes())}"),
        (e.codes() == set(), f"expected no LIVE codes, got {sorted(e.codes())}"),
        (e.top_severity is None, f"clean estate has no top severity, got {e.top_severity}"),
        (e.needle_buckets == [], f"no needle buckets expected, got {e.needle_buckets}"),
        (e.bucket_count == 9, f"expected 9 buckets, got {e.bucket_count}"),
        ("COND-SCOPED" in e.all_codes(), "should contain a condition-scoped bait"),
        ("ACL-PUBLIC-IGNORED" in e.all_codes(), "should contain an IgnorePublicAcls bait"),
        ("POLICY-PUBLIC-BLOCKED" in e.all_codes(), "should contain a BPA-neutralised public policy bait"),
    ]
    return report("replay_03_saas_tenancy_clean", e, assertions)


if __name__ == "__main__":
    sys.exit(main())
