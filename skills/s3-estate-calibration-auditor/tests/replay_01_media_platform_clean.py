"""
Replay test for fixtures/01-media-platform-clean.

Deceptive-clean estate: a 10-bucket media platform where several buckets READ as
exposed (a public ACL grant, a public-looking Principal '*' policy, Principal '*'
narrowed by org/IP, an access-point delegation) but every one is neutralised by BPA
or scoped by a Condition. The estate has NO live exposure. The failure mode this guards
against is flagging the neutralised/scoped lookalikes as live public buckets.

Stdlib only. Run with: `python tests/replay_01_media_platform_clean.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _estate import run_estate  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "01-media-platform-clean"


def main() -> int:
    e = run_estate(FIXTURE_DIR)
    assertions = [
        (e.clean, f"estate must be CLEAN (no live exposure), got live codes {sorted(e.codes())}"),
        (e.codes() == set(), f"expected no LIVE codes, got {sorted(e.codes())}"),
        (e.top_severity is None, f"clean estate has no top severity, got {e.top_severity}"),
        (e.needle_buckets == [], f"no needle buckets expected, got {e.needle_buckets}"),
        (e.bucket_count == 10, f"expected 10 buckets, got {e.bucket_count}"),
        ("POLICY-PUBLIC-BLOCKED" in e.all_codes(), "should contain a BPA-neutralised public policy bait"),
        ("ACL-PUBLIC-IGNORED" in e.all_codes(), "should contain an IgnorePublicAcls bait"),
        ("COND-SCOPED" in e.all_codes(), "should contain a condition-scoped bait"),
        (len(e.boundary) > 0, "estate should report a boundary"),
    ]
    return report("replay_01_media_platform_clean", e, assertions)


if __name__ == "__main__":
    sys.exit(main())
