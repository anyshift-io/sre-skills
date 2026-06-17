"""
Replay test for fixtures/06-analytics-estate-needle.

Single-needle estate: 10 buckets. Several use Principal '*' narrowed by a Condition
(org / external id), which are scoped and fine. Exactly one unassuming bucket
(acme-analytics-clickstream) has a Principal '*' GetObject with NO condition and BPA
NOT restricting -> LIVE public. The needle hides among the conditional lookalikes; the
only difference is a missing Condition block.

Stdlib only. Run with: `python tests/replay_06_analytics_estate_needle.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _estate import run_estate  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "06-analytics-estate-needle"


def main() -> int:
    e = run_estate(FIXTURE_DIR)
    assertions = [
        (not e.clean, "estate has a LIVE needle; must not be clean"),
        (e.codes() == {"POLICY-PUBLIC"}, f"expected exactly the public-policy needle, got {sorted(e.codes())}"),
        (e.top_severity == "critical", f"unconditional public policy is critical, got {e.top_severity}"),
        (e.needle_buckets == ["acme-analytics-clickstream"], f"the needle is acme-analytics-clickstream, got {e.needle_buckets}"),
        (len(e.live_buckets) == 1, f"exactly one live bucket, got {len(e.live_buckets)}"),
        (e.bucket_count == 10, f"expected 10 buckets, got {e.bucket_count}"),
        ("COND-SCOPED" in e.all_codes(), "should contain condition-scoped lookalikes"),
        ("POLICY-PUBLIC-BLOCKED" in e.all_codes(), "should contain a BPA-neutralised public policy bait"),
    ]
    return report("replay_06_analytics_estate_needle", e, assertions)


if __name__ == "__main__":
    sys.exit(main())
