# Worked example 1: OOM cascade in `payments-api`

A realistic OOM incident in a payment processing service, triggered by a deploy that increased per-request memory footprint. Mirrors the seven methodology steps in [`../SKILL.md`](../SKILL.md). The fixtures and replay test under `../fixtures/01-oom-cascade/` and `../tests/replay_01_oom_cascade.py` exercise this example end-to-end.

## Scenario

- **Service**: `payments-api` (HTTP service, 8 pods, behind `api-gateway`).
- **Deploy at 2026-03-12 14:18 UTC**: introduced webhook payload buffering. Per-request memory footprint went from ~80 MB to ~210 MB. Pod memory limit unchanged at 512 MB.
- **Alert fires at 14:32 UTC**: `payments_api_error_rate > 5%`.
- **Cascade**: at 14:30 the pods hit the memory limit, the orchestrator starts `OOMKill`ing them, Kubernetes restarts them, in-flight requests fail with `502`, the `api-gateway` retries failed requests (3 retries, 500 ms backoff), the retry storm doubles the incoming request rate, the still-recovering pods OOM faster, error rate climbs from 0.4% to 47% in 90 seconds.

## Step 1: anchor the window

Earliest unambiguous symptom is the alert at `2026-03-12T14:32:00Z`. No customer reports filed yet. T0 set there.

- **T0**: `2026-03-12T14:32:00Z`
- **Tnow**: `2026-03-12T14:36:00Z` (investigation triggered four minutes after the alert)
- **Window**: `[14:17:00Z, 14:36:00Z]`

The 15-minute lead-in is what catches the 14:18 deploy in step 2. Without it, the bisection in step 2 would return empty.

## Step 2: bisect the change surface

Changes overlapping the window:

| Source | Event | Time | Detail |
|---|---|---|---|
| CI/CD | Deploy `payments-api@v4.18.0` | `14:18:14Z` | Merge commit `9f3a2c1`. Diff touches `internal/webhook/buffer.go` (new payload-buffering path). |
| Terraform | (none) | | No infra changes in window. |
| IAM | (none) | | No role / policy changes in window. |
| Feature flags | (none) | | No flips in window. |
| Cron / batch | (none) | | No batch jobs in window. |

One change in window: the `payments-api` deploy 14 minutes before T0. Strong candidate for the deploy-correlator path. Need to check the OOM path in parallel (both paths can be true; OOM is often *triggered* by a deploy).

## Step 3: classify against the four reference paths

Match against the four reference paths:

- **OOM**: pod restart count climbed from 0 to 12 in the window. Orchestrator events show `OOMKilled` on 6 of 8 pods. Memory metric shows RSS at 510 MB (limit 512 MB) immediately before each OOMKill. Strong match.
- **DNS**: no `NXDOMAIN` / `SERVFAIL` in logs, no `getaddrinfo` errors, outbound latency unchanged. No match.
- **Cascading-failure**: retry count at `api-gateway` spiked 3.2x in the window. Latency on downstream `ledger-svc` calls unchanged. Cascade signature is present but is *downstream of* the OOM, not the root.
- **Deploy-correlator**: 14:18 deploy is the only change in window, diff touches the failing surface (`internal/webhook/buffer.go` is in the request path), and the new code allocates ~130 MB more per concurrent request. Strong match.

Classification: **OOM**, triggered by the deploy-correlator path. The cascading-failure signature is a second-order effect (retry storm amplifying OOM pressure), not an independent path.

## Step 4: confirm with three independent signals

Three independent signals supporting the OOM-via-deploy hypothesis:

1. **Orchestrator events** (`fixtures/01-oom-cascade/pod_events.jsonl`): `OOMKilled` on 6 of 8 pods between 14:30 and 14:35.
2. **Metrics** (`fixtures/01-oom-cascade/metrics.json`): RSS at 510 MB at 14:30:12Z, immediately before the first OOMKill.
3. **Deploy diff** (`fixtures/01-oom-cascade/deploys.json`): commit `9f3a2c1` adds a `WebhookBuffer` struct that holds full payload bodies in memory; the per-request memory increase aligns with the observed RSS jump.

A fourth signal corroborates the cascade as second-order: **traces** (`fixtures/01-oom-cascade/traces.jsonl`) show retry-storm spans from `api-gateway` only after the first OOMKill, not before.

Hypothesis confidence is high. Three signals, three independent sources.

## Step 5: quantify blast radius

- **Users affected**: 100% of payment requests fail or hit retry latency. Read-only endpoints (`GET /payments/:id`) are also affected because they share the same pods.
- **Surfaces affected**: all payment endpoints (`POST /charge`, `POST /refund`, `GET /payments/:id`, webhook callbacks).
- **Business impact**: payment processing offline. SLO burn at 12x normal rate. In a real incident, the agent should also pull the revenue-per-minute figure from the finance dashboard the user has on hand.

## Step 6: propose mitigation before root cause

Ordered recommendation:

1. **Revert** `payments-api` to `v4.17.4` (the previous successful release). The deploy is the clearly implicated change, the revert is one CI button press, and the OOM behavior should clear within one pod-restart cycle (~30 s).
2. **Feature-flag off** the webhook buffering path. Not applicable: the change shipped without a feature flag, which is itself a process gap to flag in the postmortem.
3. **Scale up** memory limit from 512 MB to 1 GB as a stopgap if revert is delayed by CI issues. Acknowledged that this does not address cause and will roughly double per-pod cost.
4. **Traffic-shift** to a previous region: not applicable, single-region service.
5. **Manual intervention** (delete pods to force fresh restarts): only if revert and scale-up are both blocked. Does not address cause; pods will OOM again within minutes.

Recommended action: **revert to `v4.17.4`**.

## Step 7: hand off

Handoff payload for `postmortem-author`:

```json
{
  "timeline": [
    {"t": "2026-03-12T14:18:14Z", "event": "Deploy payments-api@v4.18.0 (commit 9f3a2c1)"},
    {"t": "2026-03-12T14:30:12Z", "event": "First OOMKill on pod payments-api-7d9c-x4k2"},
    {"t": "2026-03-12T14:32:00Z", "event": "T0: alert payments_api_error_rate > 5% fires"},
    {"t": "2026-03-12T14:33:45Z", "event": "api-gateway retry count 3.2x baseline"},
    {"t": "2026-03-12T14:36:00Z", "event": "Tnow: investigation triggered"}
  ],
  "ranked_hypotheses": [
    {
      "path": "OOM (deploy-triggered)",
      "confidence": "high",
      "evidence": ["OOMKilled events on 6/8 pods", "RSS at memory limit", "deploy diff adds ~130MB/req via WebhookBuffer"]
    }
  ],
  "mitigation_taken": null,
  "mitigation_recommended": "Revert payments-api to v4.17.4",
  "open_questions": [
    "Why did the new WebhookBuffer path ship without a memory-footprint review?",
    "Why is there no per-request memory guardrail in the payment service load tests?"
  ]
}
```

## Why this is the OOM reference path

This example is the reference because it shows all four of these in one incident:

- A clear OOM signature at the pod level.
- A clear deploy-correlator signature (one change in window, on the failing surface).
- A clear cascading-failure signature as a second-order effect (api-gateway retry storm amplifying the primary failure).
- A safe mitigation (revert) that comes before root cause.

The methodology handles the layering: classify the primary path, note the cascade as second-order, recommend the revert. Skipping any of steps 1 through 4 produces a wrong answer (most commonly: classifying as cascading-failure and recommending circuit-breaker tuning, which does nothing to fix the OOM).
