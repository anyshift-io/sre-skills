"""
Shared reporting helper for the replay tests. Stdlib only.

Each replay_NN_*.py loads one fleet fixture, runs the reachability engine, and hands a
list of (ok, message) assertion tuples to `report`. Keeps the per-test files focused on
the ground-truth verdict that matters for that fixture (long needle path / clean).
"""

from __future__ import annotations


def report(name: str, result, assertions) -> int:
    failed = [msg for ok, msg in assertions if not ok]
    if failed:
        print(f"FAIL: {name}")
        for msg in failed:
            print(f"  - {msg}")
        return 1
    print(f"PASS: {name} ({len(assertions)} assertions)")
    codes = sorted(result.codes()) or ["none"]
    print(f"  findings: {codes} (top severity: {result.top_severity})")
    if result.shortest_path:
        print(f"  shortest path: {' -> '.join(result.shortest_path)}")
    return 0
