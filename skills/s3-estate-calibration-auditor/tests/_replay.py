"""
Shared reporting helper for the replay tests. Stdlib only.

Each replay_NN_*.py loads one fixture, runs the resolution, and hands a list of
(ok, message) assertion tuples to `report`. Keeps the per-test files focused on
the assertions that matter for that fixture.
"""

from __future__ import annotations


def report(name: str, resolution, assertions) -> int:
    failed = [msg for ok, msg in assertions if not ok]
    if failed:
        print(f"FAIL: {name}")
        for msg in failed:
            print(f"  - {msg}")
        return 1
    print(f"PASS: {name} ({len(assertions)} assertions)")
    codes = sorted(resolution.codes()) or ["none"]
    print(f"  findings: {codes} (top severity: {resolution.top_severity})")
    return 0
