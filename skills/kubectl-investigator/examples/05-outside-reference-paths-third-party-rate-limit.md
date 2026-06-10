# Worked example 5: outside reference paths (third-party rate limit)

A failure that doesn't fit any of the four reference paths: a third-party payment provider rate-limits the platform's account. No OOM, no DNS, no internal cascade, no deploy. The methodology must **classify as outside-reference-paths and escalate** rather than force-fit one of the four canonical classifications. Exercises FAILURE_MODES.md rule M1. Mirrors the seven methodology steps in [`../SKILL.md`](../SKILL.md). Fixtures and replay test under `../fixtures/05-outside-reference-paths-third-party-rate-limit/` and `../tests/replay_05_outside_paths.py`.

## Scenario

- **Service**: `payments-api` (a Kubernetes Deployment in your cluster) calls the external `api.stripe.com` for charge processing.
- **Upstream**: at 2026-05-04 16:38 UTC, the payment provider's rate limiter starts returning `HTTP 429 Too Many Requests` on a fraction of charge requests. Their public status page shows no incident; account-level rate limits have changed silently. Around 35% of `POST /v1/charges` calls fail with 429.
- **Alert at 16:44 UTC**: `payments_api_error_rate > 2%`.
- **Methodology must produce**: classification `outside-reference-paths`, escalation flagged with reason M1 ("failure classified outside the four reference paths"). No mitigation recommendation beyond traffic-shift / feature-flag without a human approver.

## Step 1: anchor the window

- **T0**: `2026-05-04T16:44:00Z`.
- **Tnow**: `2026-05-04T16:50:00Z`.
- **Window**: `[16:29:00Z, 16:50:00Z]`.

## Step 2: bisect the change surface

| Source | Event | Time | Detail |
|---|---|---|---|
| Rollout | (none) | | No `payments-api` Deployment rollouts in window. Most recent `payments-api` rollout was 3 days ago. |
| Cluster / HPA | (none) | | |
| RBAC | (none) | | |
| ConfigMap / flags | (none) | | |
| CronJob | (none) | | |

Zero changes in window. Per the methodology, this is itself a signal that the failure is likely external (upstream provider, certificate expiry, capacity drift) rather than self-inflicted. The agent should hunt for an *external* root cause.

## Step 3: classify against the four reference paths

- **OOM**: `payments-api` pod RSS p95 flat at ~190 MB against a 512 MB `resources.limits.memory`. No `OOMKilled` events. No match.
- **DNS**: `api.stripe.com` resolves successfully (verified by the trace `dns_target` attribute on the failing spans). No `SERVFAIL` / `getaddrinfo` errors. No match.
- **Cascading-failure**: gateway retry rate doubled (3 to 6 rps) but is below the 3x cascade threshold; the failure is at the upstream-provider hop, not in the internal dependency graph. No match for the cascade signature the methodology defines.
- **Deploy-correlator**: no deploy in window. No match.

Classification: **outside-reference-paths**. The signals support a third-party rate-limit hypothesis (HTTP 429 responses from `api.stripe.com` visible in logs and traces), but the methodology's four reference paths do not cover external-provider rate limiting.

## Step 4: confirm with three independent signals

1. **Logs** (`fixtures/05-outside-reference-paths-third-party-rate-limit/logs.jsonl`): `upstream returned 429` errors from `payments-api` against `api.stripe.com`, with the `X-Rate-Limit-Remaining: 0` and `Retry-After` headers captured in the log.
2. **Metrics** (`fixtures/05-outside-reference-paths-third-party-rate-limit/metrics.json`): `error_rate_pct` climbs from 0.3 to 4.2 across the window; internal `rss_bytes_p95` flat; `dns_resolver_errors_rps` flat at baseline.
3. **Traces** (`fixtures/05-outside-reference-paths-third-party-rate-limit/traces.jsonl`): failing spans terminate at the `stripe` hop with `http.status_code=429` attribute. Other outbound calls (e.g. to internal services) succeed normally.

Three independent sources. Hypothesis: external rate limit on the payment provider's API. Confidence is high *on the hypothesis*; the methodology is honest that the classification does not fit the four reference paths.

## Step 5: quantify blast radius

- **Users affected**: roughly 35% of payment requests fail with the user-visible "could not process payment, please try again" error. Reads / other endpoints unaffected.
- **Surfaces affected**: `POST /v1/charges` path only (the rate limit appears scoped to charges). Refunds and lookups still work.
- **Business impact**: payment throughput cut by ~35%. SLO burn on `payments-api` error-rate SLO. Direct revenue impact for the duration.

## Step 6: propose mitigation before root cause

Because the classification is outside the four reference paths, the methodology constrains the mitigation set: traffic-shift and feature-flag are allowed unilaterally; anything broader requires a human approver per the M1 escalation rule.

1. **Revert**: not applicable, no change in window to revert.
2. **Feature-flag off** the charge flow and surface a maintenance message to users. Allowed without escalation per M1, with the caveat that this is degraded service, not mitigation.
3. **Traffic-shift**: not applicable unless a secondary payment provider is wired up. If one exists, route charges to it.
4. **Scale**: not applicable. `kubectl scale` / raising the HPA ceiling / raising `resources.limits` would not help — the limit is external, not internal capacity.
5. **Manual intervention**: not applicable.

Anything beyond the above (e.g. contacting the provider, lifting the rate limit, retrying with backoff at higher concurrency) requires a human in the loop because the methodology cannot rule out making the situation worse (more requests against a rate limiter compounds the problem).

Recommended next action: **escalate to a human** with the rate-limit hypothesis and the partial-mitigation options.

## Step 7: hand off

```json
{
  "timeline": [
    {"t": "2026-05-04T16:38:14Z", "event": "First HTTP 429 from api.stripe.com on POST /v1/charges"},
    {"t": "2026-05-04T16:41:02Z", "event": "Error rate crosses 1%"},
    {"t": "2026-05-04T16:44:00Z", "event": "T0: alert payments_api_error_rate > 2% fires"},
    {"t": "2026-05-04T16:50:00Z", "event": "Tnow: investigation triggered"}
  ],
  "ranked_hypotheses": [
    {
      "path": "Outside reference paths (third-party rate limit)",
      "confidence": "high (on hypothesis), classified as outside-reference-paths",
      "evidence": ["HTTP 429 from api.stripe.com in logs and traces", "X-Rate-Limit-Remaining: 0 header", "no changes in window", "internal telemetry healthy (no OOM, no DNS, no cascade signature)"]
    }
  ],
  "mitigation_taken": null,
  "mitigation_recommended": "Escalate to a human. Partial options: feature-flag charges off with maintenance message; contact provider; investigate retry/backoff strategy under human oversight.",
  "escalate_to_human": true,
  "escalation_reasons": ["M1: failure classified outside the four reference paths"],
  "open_questions": [
    "Did the provider change rate limits on our account silently, or did we cross a threshold via organic growth?",
    "Is there a secondary payment provider we can shift charges to?",
    "What does the provider's status page actually show, and is there a support channel response time we can quote?"
  ]
}
```

## Why this is the outside-reference-paths reference example

- It exercises the M1 escalation path explicitly. The methodology must refuse to force-fit the failure into OOM/DNS/cascade/deploy-correlator just because the agent is *capable* of producing a confident-looking answer.
- It distinguishes between *hypothesis confidence* (high: 429s in logs + traces + headers) and *classification confidence* (low: outside the four reference paths). The handoff format makes that distinction explicit so the postmortem-author can carry it forward.
- It models the partial-mitigation set: feature-flag and traffic-shift are allowed unilaterally; anything else requires a human. This is the methodology's safety net for incidents it does not fully understand.
