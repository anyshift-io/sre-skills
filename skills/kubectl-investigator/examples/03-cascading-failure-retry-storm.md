# Worked example 3: cascading failure from upstream slowdown

A realistic cascading-failure incident: an upstream dependency (`ledger-svc`) slows down due to a DB query plan flip, the caller (`payments-api`) saturates its thread pool waiting for it, and the API gateway retry budget amplifies the failure into a wider error rate. **No code deploy, no DNS, no OOM, no infra change in window.** Mirrors the seven methodology steps in [`../SKILL.md`](../SKILL.md). Fixtures and replay test under `../fixtures/03-cascading-failure-retry-storm/` and `../tests/replay_03_cascade.py`.

## Scenario

- **Service**: `payments-api` (depends synchronously on `ledger-svc`).
- **Upstream**: `ledger-svc`'s P99 latency drifts from ~50 ms to ~180 ms over the morning; at 11:00 UTC it crosses a knee in the query-planner cost model and jumps to ~620 ms. The underlying cause is a DB table that grew past the index-only threshold, not a code change. No `ledger-svc` deploy in days.
- **Cascade**: `payments-api`'s thread pool (50 workers, ~50 ms baseline per request) saturates once requests start taking ~600 ms. Queue depth grows. New requests sit in queue then fail with `503 service unavailable`. The `api-gateway` retries (up to 3, 500 ms backoff). Retries hit the still-saturated pool, amplifying load.
- **Alert at 11:08 UTC**: `payments_api_latency_p99 > 1000ms`.
- The methodology must classify this as **cascading-failure** and recommend **circuit-breaker / traffic-shift**, not revert. There is no change to revert.

## Step 1: anchor the window

- **T0**: `2026-03-20T11:08:00Z` (alert fire).
- **Tnow**: `2026-03-20T11:15:00Z`.
- **Window**: `[10:53:00Z, 11:15:00Z]`.

## Step 2: bisect the change surface

| Source | Event | Time | Detail |
|---|---|---|---|
| Rollout | (none) | | No rollouts in window. Most recent `payments-api` deploy was 9 days ago. |
| Cluster / HPA | (none) | | |
| RBAC | (none) | | |
| ConfigMap / flags | (none) | | |
| CronJob | (none) | | |

**Zero changes in window.** Per the methodology, this is itself a strong signal: the failure is likely external (capacity, dependency, upstream provider) rather than a self-inflicted regression. The agent should *not* hunt for a phantom deploy and *should* widen the dependency-health check.

## Step 3: classify against the four reference paths

- **OOM**: `payments-api` RSS p95 flat at ~210 MB against a 512 MB limit. No `OOMKilled` events. No match.
- **DNS**: no `SERVFAIL` / `getaddrinfo` errors in logs. Outbound calls resolve normally. No match.
- **Cascading-failure**: `payments-api` thread-pool saturation warnings in logs, queue depth growing, P99 latency tripled, `api-gateway` retry rate spiked from baseline to 8x. Upstream `ledger-svc` P99 latency jumped from ~50 ms to ~620 ms inside the window. **Strong match.**
- **Deploy-correlator**: no deploy in window. No match.

Classification: **cascading-failure**. The root degradation is upstream (`ledger-svc`); the failure propagates through `payments-api` thread-pool saturation and is amplified by gateway retries.

## Step 4: confirm with three independent signals

1. **Metrics** (`fixtures/03-cascading-failure-retry-storm/metrics.json`): `upstream_latency_p99_ms` (the latency `payments-api` observes calling `ledger-svc`) climbed from 52 ms at 10:53 to 624 ms at 11:08. `payments_api_latency_p99` followed it up to 1170 ms. `gateway_retry_rate_rps` spiked from 6 baseline to 48 at T0 (8x).
2. **Application logs** (`fixtures/03-cascading-failure-retry-storm/logs.jsonl`): repeated `thread pool saturated, queue depth 142` warnings from `payments-api` starting at 11:03; `ledger client request timeout` errors from 11:04 onward; gateway 503 + retry attempt logs.
3. **Traces** (`fixtures/03-cascading-failure-retry-storm/traces.jsonl`): the slow span is consistently the `ledger-svc` hop. Pre-window baseline traces show `ledger-svc` at ~50 ms; in-window traces show 580 to 920 ms on the same span, with `payments-api` accumulating queued requests behind it.

Hypothesis confidence is high. Three independent signal sources, plus a fourth from the change-audit channel: "no changes in window" is itself a positive signal that the failure is environmental, not regression-driven.

## Step 5: quantify blast radius

- **Users affected**: P99 latency crossed 1 s for all payment requests. Around 12% of requests time out at the gateway after exhausting retry budget. Roughly 88% complete, but slowly.
- **Surfaces affected**: every endpoint on `payments-api` that touches the `ledger-svc` synchronous path (which is most of them). Downstream consumers of `payments-api` see slower responses; some upstream callers degrade silently.
- **Business impact**: latency-degraded payments. SLO burn on `payments-api` P99 latency SLO at ~6x normal. Revenue impact softer than the OOM example because most requests still complete.

## Step 6: propose mitigation before root cause

There is no change to revert. The mitigation list is therefore different from a deploy-triggered incident.

1. **Open the circuit breaker** on the `payments-api` → `ledger-svc` call path. Fail fast (return cached / degraded responses where possible) instead of letting requests queue and time out. Stops the retry storm from amplifying the upstream degradation. Does not fix `ledger-svc` itself.
2. **Shed traffic** from `payments-api`: route non-critical payment operations (e.g. async batch jobs that hit `ledger-svc`) away from the production pool, or have the gateway prefer a healthy replica if one exists. Buys time while `ledger-svc` recovers.
3. **Scale `ledger-svc` reads** (if the workload is read-heavy and the slowdown is on read paths) as a secondary stopgap. Acknowledged that this does not fix the underlying query-plan issue; it only adds capacity to absorb the slower per-request cost.
4. **Revert**: not applicable, no change in window.
5. **Manual intervention** (`kubectl rollout restart deployment/payments-api` to drain the saturated queue): only if circuit-breaker and traffic-shift are blocked. Does not address cause; the pool will saturate again within minutes if `ledger-svc` is still slow.

Recommended action: **open the circuit breaker on the `ledger-svc` call path**.

## Step 7: hand off

```json
{
  "timeline": [
    {"t": "2026-03-20T10:53:00Z", "event": "ledger-svc upstream latency p99 ~52ms (baseline)"},
    {"t": "2026-03-20T11:00:00Z", "event": "ledger-svc latency knee, p99 jumps from 180ms to 480ms"},
    {"t": "2026-03-20T11:03:30Z", "event": "First 'thread pool saturated' warning from payments-api"},
    {"t": "2026-03-20T11:04:18Z", "event": "First 'ledger client request timeout' error"},
    {"t": "2026-03-20T11:08:00Z", "event": "T0: alert payments_api_latency_p99 > 1000ms fires"},
    {"t": "2026-03-20T11:15:00Z", "event": "Tnow: investigation triggered"}
  ],
  "ranked_hypotheses": [
    {
      "path": "Cascading-failure (upstream slowdown)",
      "confidence": "high",
      "evidence": ["upstream ledger-svc p99 climbed 52ms -> 624ms", "payments-api thread pool saturation in logs", "gateway retry rate 8x baseline", "no changes in window"]
    }
  ],
  "mitigation_taken": null,
  "mitigation_recommended": "Open circuit breaker on payments-api -> ledger-svc call path",
  "open_questions": [
    "What caused the ledger-svc query-plan flip at ~11:00? Index bloat? Stats staleness? Table growth past planner threshold?",
    "Why did payments-api degrade rather than fail open? Should circuit-breaker default-state be reconsidered?",
    "Is there a tested traffic-shift path for payments-api, or is this the first time it's needed?"
  ]
}
```

## Why this is the cascading-failure reference path

- The "no change in window" signal is dispositive. An agent that biases toward "find the deploy that broke things" will hunt for a phantom deploy and waste time.
- The cascade is detectable via *upstream latency growth* even when retry rate isn't dramatic, which is the second signal pattern the methodology's `_has_cascade_signature` looks for.
- The mitigation ordering is genuinely different (circuit-breaker first, not revert), which the example proves the methodology produces correctly.

Skipping step 2 here is the most likely failure mode: an agent that doesn't enumerate "zero changes" as a signal will misclassify the incident as outside-reference-paths and escalate when in fact the cascading-failure path is the clean fit.
