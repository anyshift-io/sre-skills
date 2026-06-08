# Worked example 11: capacity-bound organic growth

A failure with no change, no provider issue, no internal cascade. The service has been growing organically for weeks and finally crossed its capacity threshold. The methodology should **recommend scaling, not revert**, because there is no change to revert and the dominant signal is request-rate growth. Exercises the "scale_resource as primary mitigation" branch for outside-paths classifications with growing traffic. Fixtures and replay test under `../fixtures/11-capacity-bound-organic-growth/` and `../tests/replay_11_capacity_bound.py`.

## Scenario

- **Service**: `search-svc` (search index queries).
- **Pattern**: request rate has been climbing organically for ~3 weeks as a marketing campaign drove user growth. Capacity was sized for ~400 rps; today's morning peak hit 720 rps. The service's query queue starts rejecting requests when it overflows. No deploy, no DNS, no internal cascade.
- **Alert at 10:55 UTC**: `search_svc_error_rate > 3%`.
- **Methodology must produce**: classification `outside-reference-paths`, blast-radius detector flags `request_rate_growing=true`, and the mitigation list leads with **scale_resource** instead of revert (no change to revert).

## Step 1: anchor the window

- **T0**: `2026-10-08T10:55:00Z`.
- **Tnow**: `2026-10-08T11:05:00Z`.
- **Window**: `[10:40:00Z, 11:05:00Z]`.

## Step 2: bisect the change surface

| Source | Event | Time | Detail |
|---|---|---|---|
| CI/CD | (none) | | |
| Terraform | (none) | | |
| IAM | (none) | | |
| Feature flags | (none) | | |
| Cron / batch | (none) | | |

Zero changes in window. Same pattern as examples 09 and 10: hunt for an external or environmental cause.

## Step 3: classify against the four reference paths

- **OOM**: RSS p95 flat at ~290 MB against 512 MB limit (~57%). No `OOMKilled`. No match.
- **DNS**: no resolution errors. No match.
- **Cascading-failure**: no upstream-latency growth. No retry-storm pattern (the rejections are from the service itself, not from cascading retries). No match.
- **Deploy-correlator**: no deploy. No match.

Classification: **outside-reference-paths**. The signature is *request-rate growth* + *internal queue saturation*, which isn't one of the four reference paths.

## Step 4: confirm with three independent signals

1. **Metrics**: `request_rate_rps` climbed from 412 at 10:40 to 718 at T0 (1.7x in 15 minutes); `error_rate_pct` from 0.3% to 4.6%; `queue_depth_p99` from 12 to 184 (15x); `rss_bytes_p95` flat at ~290 MB.
2. **Logs**: `query queue full, rejecting request` warnings from `search-svc`, climbing in frequency through the window.
3. **Traces**: failing spans show `error=queue_full` at the `search-svc` hop. The failing requests never reach the search index; they are rejected at admission.

Three independent sources. The diagnostic is clean: the service is dropping load it cannot serve.

## Step 5: quantify blast radius

- **Users affected**: ~4.6% of searches at T0, climbing as traffic climbs. Successful searches still complete normally (no latency degradation on accepted requests).
- **Surfaces affected**: search query endpoint. All other endpoints healthy.
- **Business impact**: degraded search quality (some users see "search temporarily unavailable"). No silent corruption or data loss.

The `request_rate_growing` flag is `true` in the blast radius output (rate grew >= 1.5x across the window), which triggers the scaling mitigation branch.

## Step 6: propose mitigation before root cause

Because the classification is outside-paths AND `request_rate_growing` is true, the methodology's mitigation list leads differently from a change-induced incident:

1. **Scale up** `search-svc` horizontally. Request rate has climbed past current capacity headroom; the immediate fix is more capacity. Acknowledged that capacity planning (forecasting, autoscaling tuning) is the root cause; scaling addresses the symptom.
2. **Revert**: not applicable; no change to revert.
3. **Feature-flag off**: only as a temporary degradation play if scaling is delayed. Pausing low-value search features can free queue slots.
4. **Traffic-shift**: only if a secondary search cluster exists. Same caveat as 09 and 10.
5. **Manual intervention**: not applicable.

Recommended action: **scale `search-svc` horizontally now; queue capacity planning review as a follow-up**.

## Step 7: hand off

```json
{
  "timeline": [
    {"t": "2026-10-08T10:40:00Z", "event": "request rate 412 rps (sustainable)"},
    {"t": "2026-10-08T10:48:00Z", "event": "request rate crosses 600 rps; first 'queue full' warning"},
    {"t": "2026-10-08T10:55:00Z", "event": "T0: alert search_svc_error_rate > 3% fires; request rate 692 rps"},
    {"t": "2026-10-08T11:05:00Z", "event": "Tnow: investigation triggered; request rate 718 rps, error rate 4.6%"}
  ],
  "ranked_hypotheses": [
    {
      "path": "Capacity-bound organic growth (outside reference paths)",
      "confidence": "high (on hypothesis), classified as outside-reference-paths",
      "evidence": ["request rate grew 412 -> 718 rps (1.7x) across window", "queue_depth_p99 grew 12 -> 184 (15x)", "query queue full warnings in logs", "no changes in window", "RSS / cpu / DNS / cascade signatures absent"]
    }
  ],
  "mitigation_taken": null,
  "mitigation_recommended": "Scale search-svc horizontally to absorb the new traffic level. Capacity planning review as a follow-up.",
  "escalate_to_human": true,
  "escalation_reasons": ["M1: failure classified outside the four reference paths"],
  "open_questions": [
    "Why did autoscaling not kick in? Are the autoscale thresholds tuned to absolute capacity instead of queue saturation?",
    "Is the 3-week request-rate climb visible in a forecast dashboard? If not, where would it have been caught?",
    "What is the upper bound on this service's horizontal scaling? Are downstream dependencies (search index shards) also at risk?"
  ]
}
```

## Why this is the capacity-bound reference example

- It models the case where the methodology's *default mitigation* (revert) is structurally wrong. There is no change to revert; recommending one would be a confident-looking error.
- It exercises the `request_rate_growing` blast-radius signal, which is the methodology's mechanism for detecting saturation in the absence of a discrete event.
- It surfaces a class of incidents where the underlying cause is operational (capacity planning) rather than software-defect. The methodology surfaces this honestly via outside-paths classification and scaling mitigation, instead of inventing a software hypothesis to explain the error rate.
