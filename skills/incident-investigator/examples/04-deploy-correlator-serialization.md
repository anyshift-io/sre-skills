# Worked example 4: pure deploy-correlator (serialization regression)

A realistic deploy-correlator incident: a deploy ships a serialization change that returns binary-encoded responses on an endpoint whose downstream consumers expect JSON. **Not OOM, not DNS, not a cascade.** A clean deploy-correlator signature: one change in window, on the failing surface, with the deploy diff explaining the failure mode. Mirrors the seven methodology steps in [`../SKILL.md`](../SKILL.md). Fixtures and replay test under `../fixtures/04-deploy-correlator-serialization/` and `../tests/replay_04_deploy_correlator.py`.

## Scenario

- **Service**: `checkout-api`. The `GET /cart/:id` endpoint returns the user's current cart contents to multiple downstream consumers (web frontend, mobile apps, partner widgets).
- **Deploy at 2026-02-15 13:12 UTC**: shipped a "performance" change that switched the `/cart/:id` response from JSON to a binary Protobuf encoding behind the same `Content-Type: application/json` header. The change was wrapped in a feature flag during development but the flag was removed in the final PR. None of the downstream consumers can decode Protobuf, so they fail to parse the response and surface errors back to users.
- **Alert at 13:25 UTC**: `checkout_api_error_rate > 2%`.
- **What the methodology must produce**: classify as **deploy-correlator** (not OOM, not DNS, not cascade), recommend reverting the deploy. The deploy diff explicitly touches the failing surface (`/cart/:id` serialization), which is the M4 confirmation-bias guard satisfied.

## Step 1: anchor the window

- **T0**: `2026-02-15T13:25:00Z` (alert fire).
- **Tnow**: `2026-02-15T13:30:00Z`.
- **Window**: `[13:10:00Z, 13:30:00Z]`.

The 15-minute lead-in catches the 13:12 deploy, 13 minutes before T0.

## Step 2: bisect the change surface

| Source | Event | Time | Detail |
|---|---|---|---|
| CI/CD | Deploy `checkout-api@v6.4.0` | `13:12:08Z` | Commit `d1c4e22`. Diff: `internal/serializer/cart.go` switches response encoding from JSON to Protobuf for the `/cart/:id` endpoint. |
| Terraform | (none) | | |
| IAM | (none) | | |
| Feature flags | (none) | | The PR description mentions a flag was removed before merge. |
| Cron / batch | (none) | | |

One change in window. The diff explicitly touches the endpoint the consumers are calling, which is the M4 (deploy-correlator confirmation bias) guard: deploy-correlator is only the right classification when the deploy diff actually intersects the failing surface, not just because the timing lines up.

## Step 3: classify against the four reference paths

- **OOM**: RSS p95 flat at ~140 MB against a 512 MB limit. No `OOMKilled` events. No match.
- **DNS**: no `SERVFAIL` / `getaddrinfo` errors. Outbound calls resolve normally. No match.
- **Cascading-failure**: gateway retry rate goes from 3 rps baseline to ~5 rps after the deploy. That's a 1.7x increase, well below the cascade threshold (3x). Upstream latency unchanged (no slow dependency). No match.
- **Deploy-correlator**: 13:12 deploy is the only change in window; diff touches `/cart/:id` serialization; downstream consumers report `unexpected EOF` / `failed to parse response` errors in the window. **Strong match.**

Classification: **deploy-correlator**.

## Step 4: confirm with three independent signals

1. **Metrics** (`fixtures/04-deploy-correlator-serialization/metrics.json`): `error_rate_pct` jumps from 0.3% baseline to 4.8% at T0; `request_rate_rps` flat (the failure is not amplifying traffic). `gateway_retry_rate_rps` only 1.7x baseline (no cascade signature). RSS flat (no OOM signature).
2. **Logs** (`fixtures/04-deploy-correlator-serialization/logs.jsonl`): downstream consumer services log `unexpected EOF parsing JSON` and `failed to parse application/json response from checkout-api` starting 90 s after the deploy.
3. **Deploy diff** (`fixtures/04-deploy-correlator-serialization/deploys.json`): commit `d1c4e22` switches the `/cart/:id` response encoding from JSON to Protobuf while keeping the `Content-Type: application/json` header.
4. **Traces** (`fixtures/04-deploy-correlator-serialization/traces.jsonl`): `checkout-api` spans complete successfully (the service returns 200s); the failure is at the *consumer* span, which decodes the response and errors out. This is diagnostic: a server-side OOM or upstream-cascade incident would have failing spans on the `checkout-api` hop.

Four independent signal sources. Confidence high.

## Step 5: quantify blast radius

- **Users affected**: every user whose client calls `GET /cart/:id` and parses the response as JSON. Conservatively 100% of cart fetches, but the failure is silent for some clients that accept arbitrary bytes and only surface when the cart UI tries to render.
- **Surfaces affected**: `/cart/:id` endpoint, plus any code path that depends on the cart payload being JSON-decodable. Web frontend cart page, mobile app cart screen, partner-widget cart integration. The endpoint itself responds 200.
- **Business impact**: checkout funnel partially blocked (users cannot see their cart contents). SLO impact on the checkout success-rate SLO, not on the `checkout-api` availability SLO.

## Step 6: propose mitigation before root cause

1. **Revert** `checkout-api` to `v6.3.7` (the previous successful release, commit `b09d318`). The deploy is the clearly implicated change, the revert is one CI button press, and downstream consumers will start decoding successfully on the next request.
2. **Feature-flag off** the new serialization path. Not applicable: the PR description confirms the flag was removed before merge. Adding the flag back would itself be a code change with its own deploy cycle and is slower than reverting.
3. **Scale**: not applicable. The failure is not capacity-bound.
4. **Traffic-shift**: not applicable. No canary / blue-green / regional split is configured for this service.
5. **Manual intervention** (kill request mid-flight): does not address cause. Skip.

Recommended action: **revert to `v6.3.7`**.

## Step 7: hand off

```json
{
  "timeline": [
    {"t": "2026-02-15T13:12:08Z", "event": "Deploy checkout-api@v6.4.0 (commit d1c4e22)"},
    {"t": "2026-02-15T13:13:42Z", "event": "First 'failed to parse application/json response' from web frontend"},
    {"t": "2026-02-15T13:25:00Z", "event": "T0: alert checkout_api_error_rate > 2% fires"},
    {"t": "2026-02-15T13:30:00Z", "event": "Tnow: investigation triggered"}
  ],
  "ranked_hypotheses": [
    {
      "path": "Deploy-correlator (serialization regression)",
      "confidence": "high",
      "evidence": ["deploy v6.4.0 in window touches /cart/:id encoding", "consumer-side parse errors in logs", "checkout-api spans return 200 (failure is consumer-side)", "no OOM / DNS / cascade signature"]
    }
  ],
  "mitigation_taken": null,
  "mitigation_recommended": "Revert checkout-api to v6.3.7",
  "open_questions": [
    "Why was the feature flag removed in the final PR? Was it reviewed?",
    "Why didn't the contract test between checkout-api and its consumers catch the encoding switch?",
    "Are there other Content-Type-honest serialization paths in the codebase that could regress the same way?"
  ]
}
```

## Why this is the deploy-correlator reference path

- It is a *clean* deploy-correlator: no OOM, no DNS, no cascade. The methodology must reach deploy-correlator without being tempted into OOM-via-deploy (which is what example 01 tests).
- It exercises the M4 confirmation-bias guard: the deploy isn't just temporally correlated; the diff explicitly touches the failing surface, and the failure shape (consumer-side parse errors with successful 200s upstream) matches the diff's stated change. An agent that classified on timing alone would be vulnerable.
- It exercises the case where mitigation is unambiguously revert (one change, isolated, reversible), in contrast to example 07 where a bundled deploy makes revert blast radius unsafe.
