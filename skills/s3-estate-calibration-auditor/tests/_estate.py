"""
Deterministic ground-truth engine for the s3-estate-calibration-auditor screening harness.

This module REUSES the already-validated per-bucket engine from the sibling skill
`s3-access-auditor` verbatim. The proven four-layer resolution logic (BPA x bucket policy x
bucket ACL x access points) lives in `_resolve.py`, a byte-for-byte copy of that skill's
`tests/_resolve.py`. We do NOT change the engine. Ground truth here is therefore provably the
same computation, applied bucket-by-bucket and then aggregated across the estate.

What this file adds is the ESTATE aggregation the screening harness needs. Each fixture in
this harness is not a single bucket but an ESTATE: a directory of ~8-12 bucket sub-directories,
each in the exact `s3-access-auditor` input shape (`public-access-block.json` /
`bucket-policy.json` / `bucket-acl.json` / optional `access-points.json` / `meta.json`).
`run_estate(fixture_dir)` runs the verbatim per-bucket `run_resolve` on every bucket, then rolls
the per-bucket Resolutions up into one estate verdict:

    .buckets          list[Resolution]            (one verbatim run_resolve per bucket sub-dir)
    .live_buckets     list[Resolution]            (buckets with at least one LIVE finding)
    .clean            bool                         (estate has NO live exposure anywhere)
    .codes()          set[str]                     (union of live finding codes across the estate)
    .top_severity     "critical"|"high"|... | None (worst live severity across the estate)
    .boundary         list[str]                    (the joins the bucket configs cannot make)
    .needle_buckets   list[str]                    (names of the buckets carrying the live needle)

LIVE vs NEUTRALISED is the whole point of this calibration harness. The per-bucket engine emits
`POLICY-PUBLIC-BLOCKED`, `ACL-PUBLIC-IGNORED`, and `COND-SCOPED` for buckets that READ as exposed
but are genuinely neutralised by BPA or scoped by a Condition: those carry NO live exposure. A
bucket is "live" only if it carries a code in `_LIVE_CODES` (a real public or cross-account
grant). The estate is clean iff no bucket is live. The deceptive-clean estates in this harness
are full of buckets that trip the neutralised/scoped codes but are NOT live; the needle estates
hide exactly one live bucket among many neutralised/scoped ones.

Stdlib only. No external dependencies. No credentials. Python 3.10+.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Re-export the proven per-bucket engine's public surface unchanged.
from _resolve import (  # noqa: E402
    Finding,
    Resolution,
    run_resolve,
)

__all__ = ["run_estate", "Estate", "Finding", "Resolution", "run_resolve", "LIVE_CODES"]

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

# The finding codes that mean a bucket carries LIVE exposure (a real public or cross-account
# grant that is in effect right now). Everything else the engine can emit
# (POLICY-PUBLIC-BLOCKED, ACL-PUBLIC-IGNORED, COND-SCOPED) reads as exposed but is genuinely
# neutralised by BPA or scoped by a Condition -- NOT live. This distinction is the calibration
# the harness measures: the cold agent must not flag the neutralised/scoped codes as live.
LIVE_CODES = frozenset({
    "POLICY-PUBLIC",   # critical: public bucket policy, BPA not restricting
    "AP-PUBLIC",       # critical: public access-point policy
    "XACCT-POLICY",    # high: cross-account bucket policy, survives BPA
    "XACCT-ACL",       # high: cross-account canonical-user ACL grant, survives BPA
    "ACL-PUBLIC",      # high: public-group ACL grant, IgnorePublicAcls off
})


@dataclass
class Estate:
    """Estate-wide roll-up of per-bucket Resolutions. The aggregation across sub-items."""

    estate: str
    buckets: list[Resolution] = field(default_factory=list)
    boundary: list[str] = field(default_factory=list)

    def _live_findings(self, res: Resolution) -> list[Finding]:
        return [f for f in res.findings if f.code in LIVE_CODES]

    @property
    def live_buckets(self) -> list[Resolution]:
        """Buckets carrying at least one LIVE finding (real public / cross-account grant)."""
        return [b for b in self.buckets if self._live_findings(b)]

    @property
    def clean(self) -> bool:
        """The estate is clean iff NO bucket carries a live finding. Neutralised /
        scoped buckets (POLICY-PUBLIC-BLOCKED, ACL-PUBLIC-IGNORED, COND-SCOPED) do not
        count as live exposure."""
        return len(self.live_buckets) == 0

    def codes(self) -> set[str]:
        """Union of LIVE finding codes across the estate (the codes that matter)."""
        out: set[str] = set()
        for b in self.buckets:
            out |= {f.code for f in self._live_findings(b)}
        return out

    def all_codes(self) -> set[str]:
        """Union of ALL finding codes (live + neutralised + scoped) across the estate."""
        out: set[str] = set()
        for b in self.buckets:
            out |= b.codes()
        return out

    @property
    def top_severity(self) -> str | None:
        """Worst LIVE severity across the estate, or None if the estate is clean."""
        live = [f for b in self.buckets for f in self._live_findings(b)]
        if not live:
            return None
        return min(live, key=lambda f: _SEVERITY_RANK[f.severity]).severity

    @property
    def needle_buckets(self) -> list[str]:
        """Names of the buckets carrying the live needle (sorted, stable)."""
        return sorted(b.bucket for b in self.live_buckets)

    @property
    def bucket_count(self) -> int:
        return len(self.buckets)


def _bucket_dirs(fixture_dir: Path) -> list[Path]:
    """The bucket sub-directories of an estate fixture: any child dir that carries at least
    one of the four config files. Sorted by name for a stable order."""
    dirs = []
    for child in sorted(fixture_dir.iterdir()):
        if not child.is_dir():
            continue
        if any((child / f).exists() for f in (
            "public-access-block.json", "bucket-policy.json", "bucket-acl.json", "access-points.json",
        )):
            dirs.append(child)
    return dirs


def _estate_boundary(buckets: list[Resolution]) -> list[str]:
    """Estate-level boundary: the joins no per-bucket config can make, stated once. Drawn
    from the per-bucket boundary notes (deduped) plus the estate-scale caveat."""
    notes: list[str] = [
        "This is a static read of each bucket's config. Whether a flagged grant is actually "
        "EXPLOITABLE depends on what the trusted principals can do and on the data's sensitivity, "
        "neither of which is in a bucket config. Reachability-on-paper is not exposure-in-fact.",
    ]
    seen = set(notes)
    for b in buckets:
        for note in b.boundary:
            if note not in seen:
                notes.append(note)
                seen.add(note)
    return notes


def run_estate(fixture_dir: Path) -> Estate:
    """Run the verbatim per-bucket engine over every bucket in the estate, then aggregate.

    For this estate harness the "aggregation across sub-items" is: run the proven
    `run_resolve` on each bucket sub-directory (no engine change), then roll up the
    per-bucket Resolutions into one estate verdict -- clean iff no bucket is live, the
    needle being whichever bucket(s) carry a live finding among many neutralised/scoped ones.
    This is the ground-truth oracle the screening harness anchors its LLM judge against.
    """
    fixture_dir = Path(fixture_dir)
    meta = {}
    meta_path = fixture_dir / "meta.json"
    if meta_path.exists():
        import json
        meta = json.loads(meta_path.read_text())
    estate_name = meta.get("estate", fixture_dir.name)

    buckets = [run_resolve(d) for d in _bucket_dirs(fixture_dir)]
    return Estate(
        estate=estate_name,
        buckets=buckets,
        boundary=_estate_boundary(buckets),
    )
