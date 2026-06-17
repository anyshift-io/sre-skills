"""
Replay test for fixtures/02-data-lake-clean.

Deceptive-clean estate: an 11-bucket data lake. Multiple buckets carry public-looking
policies and a public ACL grant, all neutralised by BPA or scoped by Conditions
(org path, external id). NO live exposure. Guards against over-flagging the neutralised
lake buckets as live.

Stdlib only. Run with: `python tests/replay_02_data_lake_clean.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _estate import run_estate  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "02-data-lake-clean"


def main() -> int:
    e = run_estate(FIXTURE_DIR)
    assertions = [
        (e.clean, f"estate must be CLEAN, got live codes {sorted(e.codes())}"),
        (e.codes() == set(), f"expected no LIVE codes, got {sorted(e.codes())}"),
        (e.top_severity is None, f"clean estate has no top severity, got {e.top_severity}"),
        (e.needle_buckets == [], f"no needle buckets expected, got {e.needle_buckets}"),
        (e.bucket_count == 11, f"expected 11 buckets, got {e.bucket_count}"),
        ("POLICY-PUBLIC-BLOCKED" in e.all_codes(), "should contain a BPA-neutralised public policy bait"),
        ("ACL-PUBLIC-IGNORED" in e.all_codes(), "should contain an IgnorePublicAcls bait"),
        ("COND-SCOPED" in e.all_codes(), "should contain a condition-scoped bait"),
    ]
    return report("replay_02_data_lake_clean", e, assertions)


if __name__ == "__main__":
    sys.exit(main())
