# Worked example 10: multi-region asymmetry (config drift)

The same image tag runs in two regional Kubernetes clusters. One cluster fails, the other does not. The methodology must **surface the regional asymmetry as a first-class signal** instead of force-fitting OOM/DNS/cascade on aggregate metrics that hide the asymmetry. Escalates with a regional-asymmetry reason and a config-drift hypothesis. Fixtures and replay test under `../fixtures/10-multi-region-asymmetry/` and `../tests/replay_10_multi_region.py`.

## Scenario

- **Service**: `image-svc`. The same image tag (same code) runs in two regional clusters, `us-east-1` and `us-west-2`.
- **Failure**: `us-east-1` error rate climbs from 0.3% to 25%. `us-west-2` stays at baseline (~0.3%). The image tags are identical, so it cannot be a code regression.
- **Underlying cause** (which the methodology surfaces as a hypothesis, not as a confirmed root cause): per-cluster config drift. The `us-east-1` cluster's ConfigMap/GitOps overlay was never reconciled — an Argo CD sync failed silently and was never retried — leaving `image-svc` in that cluster pointing at a stale in-cluster object-store Service (`image-store`) that has no ready endpoints, while `us-west-2` points at the correct Service. The failure only surfaced today because of cache invalidation upstream.
- **Alert at 11:42 UTC**: aggregate `image_svc_error_rate > 5%` (the aggregate is dragged up by `us-east-1`'s share of traffic).
- **Methodology must produce**: detection of the per-region asymmetry, classification `outside-reference-paths` (no single reference path explains it), escalation with the regional-asymmetry reason, and a config-drift hypothesis in the handoff.

## Step 1: anchor the window

- **T0**: `2026-09-14T11:42:00Z`.
- **Tnow**: `2026-09-14T11:50:00Z`.
- **Window**: `[11:27:00Z, 11:50:00Z]`.

## Step 2: bisect the change surface

| Source | Event | Time | Detail |
|---|---|---|---|
| Rollout | (none) | | |
| Cluster / HPA | (none in window) | | |
| RBAC | (none) | | |
| ConfigMap / flags | (none) | | |
| CronJob | (none) | | |

Zero changes in window. As with example 09, this points to an external or environmental cause. The regional asymmetry, surfaced in step 4, narrows the hypothesis space further.

## Step 3: classify against the four reference paths

Run the classifier on aggregate metrics first:

- **OOM**: aggregate RSS p95 flat. No `OOMKilled` events. No match.
- **DNS**: the `image-store.storage.svc.cluster.local` Service name resolves; the failure is `no endpoints available`, not a DNS `SERVFAIL`. No match.
- **Cascading-failure**: no cascade signature. No match.
- **Deploy-correlator**: no rollout. No match.

Classification: **outside-reference-paths**. The four reference paths do not have a `regional-asymmetry` shape.

## Step 4: confirm with three independent signals

1. **Logs**: `image-svc` in `us-east-1` logs `image fetch failed: Get "http://image-store.storage.svc.cluster.local/o/raw": no endpoints available for service "image-store"`. `us-west-2` logs no such errors.
2. **Metrics (regional)**: per-region samples (`fixtures/10-multi-region-asymmetry/metrics.json`) show `us-east-1` error rate 25% vs `us-west-2` error rate 0.3% over the window. **Regional asymmetry detector trips** with a 50x+ ratio.
3. **Traces**: failing spans only originate from pods in the `us-east-1` cluster, terminating at the in-cluster `image-store` Service hop with `http.status_code=503` / `error=NoEndpoints`. `us-west-2` pods serve identical requests successfully.

Three independent signal sources. The methodology's regional-asymmetry detector surfaces this as an additional structured signal in the handoff.

## Step 5: quantify blast radius

- **Users affected**: roughly the share of traffic served by the `us-east-1` cluster (typically ~60% in this topology). Users routed to `us-west-2` are unaffected.
- **Surfaces affected**: image processing endpoints in the `us-east-1` cluster.
- **Business impact**: ~60% of image uploads fail. Read-only image fetches degraded.

## Step 6: propose mitigation before root cause

Because the classification is outside-paths and a regional asymmetry is detected, the methodology's mitigation options shift:

1. **Traffic-shift** all `image-svc` traffic to the `us-west-2` cluster while `us-east-1` is investigated. Allowed without escalation (it is the canonical "traffic-shift away from failing region" move).
2. **Investigate config drift** in the `us-east-1` cluster. Compare the `image-svc` ConfigMap/GitOps overlay against `us-west-2` to identify the stale `image-store` Service reference, and check Argo CD sync status for the silently failed reconcile. This requires a human in the loop.
3. **`kubectl rollout undo`**: not applicable (no rollout or change in window).
4. **Scale**: not applicable.

Recommended next action: **traffic-shift to the `us-west-2` cluster immediately**, then escalate the config-drift investigation to a human.

## Step 7: hand off

```json
{
  "timeline": [
    {"t": "2026-09-14T11:32:00Z", "event": "First 'no endpoints available for service image-store' error in us-east-1"},
    {"t": "2026-09-14T11:42:00Z", "event": "T0: aggregate image_svc_error_rate > 5% fires"},
    {"t": "2026-09-14T11:50:00Z", "event": "Tnow: investigation triggered"}
  ],
  "ranked_hypotheses": [
    {
      "path": "ConfigMap/GitOps Service drift between us-east-1 and us-west-2 clusters (outside reference paths)",
      "confidence": "high (on hypothesis); classification outside-reference-paths",
      "evidence": ["per-region error rate 25% (us-east-1) vs 0.3% (us-west-2)", "'no endpoints available for service image-store' errors only from us-east-1 pods", "same image tag running in both clusters", "zero changes in window"]
    }
  ],
  "mitigation_taken": null,
  "mitigation_recommended": "Traffic-shift to us-west-2 cluster while ConfigMap/GitOps Service-drift investigation runs.",
  "regional_asymmetry": {
    "detected": true,
    "per_region_peak_error_rate_pct": {"us-east-1": 25.0, "us-west-2": 0.3},
    "asymmetry_ratio": 83.3
  },
  "escalate_to_human": true,
  "escalation_reasons": [
    "M1: failure classified outside the four reference paths",
    "regional-asymmetry detected with 83x ratio"
  ],
  "open_questions": [
    "Why did the Argo CD sync for the us-east-1 cluster fail silently three weeks ago? Where is the missing sync-failed alert?",
    "Are other workloads in the us-east-1 cluster pointing at the same stale image-store Service, or otherwise unreconciled?",
    "Should config drift checks run as a daily cross-cluster GitOps/ConfigMap diff job?"
  ]
}
```

## Why this is the multi-region-asymmetry reference example

- It exposes the failure mode where *aggregate metrics hide the truth*. An agent that classifies on aggregate signals would see a moderate error rate and miss the diagnostic that only one cluster is affected.
- It exercises the regional-asymmetry detector, which is the methodology's mechanism for surfacing per-region patterns as a first-class signal in the handoff.
- It models a class of operational reality (ConfigMap/GitOps drift across clusters) that the four reference paths do not directly cover, requiring the methodology to escalate honestly rather than guess.
