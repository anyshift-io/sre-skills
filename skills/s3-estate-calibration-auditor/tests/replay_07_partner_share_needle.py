"""
Replay test for fixtures/07-partner-share-needle.

Single-needle estate: 9 buckets. Several carry an AllUsers public ACL grant that is
IGNORED by IgnorePublicAcls (not live). Exactly one bucket (acme-share-partner-drop)
grants READ to a different account's CANONICAL USER via ACL: IgnorePublicAcls only
neutralises the public GROUPS, so a cross-account canonical-user grant stays LIVE even
with BPA tightened. The needle is a single ACL grant that looks like the ignored public
ones but is a named other identity.

Stdlib only. Run with: `python tests/replay_07_partner_share_needle.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _estate import run_estate  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "07-partner-share-needle"


def main() -> int:
    e = run_estate(FIXTURE_DIR)
    assertions = [
        (not e.clean, "estate has a LIVE needle; must not be clean"),
        (e.codes() == {"XACCT-ACL"}, f"expected exactly the cross-account-ACL needle, got {sorted(e.codes())}"),
        (e.top_severity == "high", f"cross-account ACL grant is high, got {e.top_severity}"),
        (e.needle_buckets == ["acme-share-partner-drop"], f"the needle is acme-share-partner-drop, got {e.needle_buckets}"),
        (len(e.live_buckets) == 1, f"exactly one live bucket, got {len(e.live_buckets)}"),
        (e.bucket_count == 9, f"expected 9 buckets, got {e.bucket_count}"),
        ("ACL-PUBLIC" not in e.codes(), "the needle is a cross-account canonical user, NOT a public group"),
        ("ACL-PUBLIC-IGNORED" in e.all_codes(), "should contain the ignored-public-ACL lookalikes"),
        ("COND-SCOPED" in e.all_codes(), "should contain a condition-scoped bait"),
        ("POLICY-PUBLIC-BLOCKED" in e.all_codes(), "should contain a BPA-neutralised public policy bait"),
    ]
    return report("replay_07_partner_share_needle", e, assertions)


if __name__ == "__main__":
    sys.exit(main())
