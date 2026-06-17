"""
Replay test for fixtures/05-logging-estate-needle.

Single-needle estate: 11 buckets, exactly one with a LIVE cross-account bucket policy.
The needle (acme-log-shipping) has BPA all on -- which reads as locked down -- but the
policy grants a named other account (905638217741) read. Cross-account is NOT public, so
BPA does not block it: the grant stays live. Everything else is clean or neutralised.

Stdlib only. Run with: `python tests/replay_05_logging_estate_needle.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _estate import run_estate  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "05-logging-estate-needle"


def main() -> int:
    e = run_estate(FIXTURE_DIR)
    assertions = [
        (not e.clean, "estate has a LIVE needle; must not be clean"),
        (e.codes() == {"XACCT-POLICY"}, f"expected exactly the cross-account-policy needle, got {sorted(e.codes())}"),
        (e.top_severity == "high", f"cross-account access is high, got {e.top_severity}"),
        (e.needle_buckets == ["acme-log-shipping"], f"the needle is acme-log-shipping, got {e.needle_buckets}"),
        (len(e.live_buckets) == 1, f"exactly one live bucket, got {len(e.live_buckets)}"),
        (e.bucket_count == 11, f"expected 11 buckets, got {e.bucket_count}"),
        ("POLICY-PUBLIC" not in e.codes(), "the needle is cross-account, NOT public"),
        ("POLICY-PUBLIC-BLOCKED" in e.all_codes(), "should still contain neutralised baits"),
        ("ACL-PUBLIC-IGNORED" in e.all_codes(), "should still contain an ignored-ACL bait"),
        ("COND-SCOPED" in e.all_codes(), "should still contain a condition-scoped bait"),
    ]
    return report("replay_05_logging_estate_needle", e, assertions)


if __name__ == "__main__":
    sys.exit(main())
