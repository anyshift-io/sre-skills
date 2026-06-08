# Replay tests for `incident-investigator`

Stdlib-only Python tests that exercise the methodology in [`../SKILL.md`](../SKILL.md) against committed fixtures. No external credentials required.

## Running the tests

From the skill directory (`skills/incident-investigator/`):

```bash
for t in tests/replay_*.py; do python "$t" || exit 1; done
```

Each test prints `PASS` or `FAIL` and exits with the appropriate code. The current suite has 11 tests covering the four reference paths, the FAILURE_MODES escalation rules (M1, M2, M3, M4), and edge cases (zero changes in window, multi-region asymmetry, capacity saturation), totalling 99 assertions. Wire them into CI as plain `python` invocations.

## What the tests assert

Each replay test loads the fixtures for one worked example, runs the reference methodology (`_methodology.py`) end-to-end against them, and asserts:

- The investigation window is anchored correctly (step 1).
- The change surface contains the expected change(s) (step 2).
- The failure is classified into the right reference path (step 3).
- At least three independent signal sources are confirmed (step 4).
- The blast-radius numbers fall in the expected range (step 5).
- The recommended mitigation is correct, with the right action ordering (step 6).
- The handoff payload is well-formed and the escalation flag matches expectations (step 7).

A test fails when the methodology regresses on any of these. Treat a failed replay test as a regression in `SKILL.md` or in the reference implementation, not a test bug.

## Fixture schema

Each example has its own fixture directory under `../fixtures/<example-slug>/`. Files are committed JSON / JSONL with no external dependencies.

| File | Format | Purpose |
|---|---|---|
| `deploys.json` | JSON | Single object with `deploys`, `infra_changes`, `iam_changes`, `feature_flags`, `scheduled_jobs` arrays. Each event has a timestamp field (`deployed_at`, `changed_at`, `flipped_at`, `ran_at`) and a `diff_summary` string. |
| `pod_events.jsonl` | JSONL (optional) | Orchestrator pod events. One JSON object per line with `t`, `pod`, `reason`, `message`. Skip if the example is not pod-level. |
| `metrics.json` | JSON | Time-series snapshot. Fields: `service`, `memory_limit_bytes`, `samples[]`. Each sample has `t`, `rss_bytes_p95`, `error_rate_pct`, `request_rate_rps`, `gateway_retry_rate_rps`, and any path-specific counter (e.g. `dns_resolver_errors_rps`). |
| `logs.jsonl` | JSONL (optional) | Application or system logs. One JSON object per line with `t`, `level`, `service`, `msg`, and any path-specific fields. |
| `traces.jsonl` | JSONL (optional) | Distributed traces. One JSON object per line with `t`, `trace_id`, `request_id`, `spans[]`, `outcome`, `retries`. |

The reference implementation (`_methodology.py`) gracefully handles missing optional files (returns empty lists).

## Adding a new replay test

When you contribute a new worked example to the skill:

1. Drop fixtures under `../fixtures/<example-slug>/` following the schema above.
2. Add `replay_NN_<example-slug>.py` in this directory, modeled on the existing two.
3. Pick assertions that cover the seven methodology steps. Existing tests range from 6 to 13 assertions. New tests typically want 7 to 15.
4. Run locally, commit, and reference the test in the example's markdown narrative.

A new test that does not exercise at least one independent signal source the existing tests do not exercise will fail review. The point of the replay corpus is breadth.

## Why stdlib only

Skills get adopted when they run anywhere with zero setup. A `pip install` is an adoption tax. The reference implementation uses only `datetime`, `json`, `pathlib`, `dataclasses`, and `typing`. If a future test requires a third-party dependency (e.g. `pytest`), that's a signal the methodology is leaking implementation detail.

## Future: agent-shaped tests

The reference implementation in `_methodology.py` is a deterministic stand-in. A natural follow-up is to run the same fixtures through an actual LLM agent loaded with `SKILL.md` and assert the agent produces the same classification + mitigation. That work is out of scope for the first reference example; contributions welcome.
