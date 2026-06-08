# Worked example 2: DNS resolution failure in `inventory-svc`

A realistic DNS incident in an internal HTTP service caused by a typo in a CoreDNS `Corefile` ConfigMap update. Mirrors the seven methodology steps in [`../SKILL.md`](../SKILL.md). Fixtures and replay test under `../fixtures/02-dns-resolution-failure/` and `../tests/replay_02_dns.py`.

## Scenario

- **Service**: `inventory-svc` (HTTP service, calls upstream `catalog-svc.internal:8080`).
- **Infra change at 2026-04-08 09:32 UTC**: `Corefile` ConfigMap updated to add a new `.internal` forward. The change introduced a typo in the upstream resolver IP, breaking resolution for `*.internal` zones intermittently (about 30% of queries returned `SERVFAIL`).
- **Alert fires at 09:47 UTC**: `inventory_svc_error_rate > 3%`.
- **No code deploy in window**. The change surface in step 2 contains only the ConfigMap update.

## Step 1: anchor the window

- **T0**: `2026-04-08T09:47:00Z` (alert fire).
- **Tnow**: `2026-04-08T09:53:00Z` (investigation triggered).
- **Window**: `[09:32:00Z, 09:53:00Z]`.

The 15-minute lead-in catches the 09:32 ConfigMap update. Without it, the change surface would return empty and the agent would risk misclassifying as a flaky-network external failure.

## Step 2: bisect the change surface

| Source | Event | Time | Detail |
|---|---|---|---|
| CI/CD | (none) | | No code deploys in window. |
| Terraform / kubectl | `kube-system/coredns` Corefile ConfigMap updated | `09:32:18Z` | Added `forward .internal 10.100.0.53` line; typo: should be `10.100.0.5`. |
| IAM | (none) | | |
| Feature flags | (none) | | |
| Cron / batch | (none) | | |

One change in window: an infrastructure change to the cluster's DNS configuration. The fact that *zero* code deploys touched `inventory-svc` is itself a signal pushing away from the deploy-correlator path and toward an environmental cause.

## Step 3: classify against the four reference paths

- **OOM**: no `OOMKilled` events, memory metrics flat at baseline. No match.
- **DNS**: 47 `SERVFAIL` log lines for `catalog-svc.internal` in window, `getaddrinfo: Name or service not known` errors in client logs, recent change to CoreDNS configuration. Strong match.
- **Cascading-failure**: retry counts elevated but pattern is intermittent (correlates with the ~30% SERVFAIL rate), not the saturating-thread-pool shape of a true cascade. Match is weak; signature is downstream of DNS.
- **Deploy-correlator**: no application-code deploys in window. No match against `inventory-svc`. The CoreDNS configuration *change* is structurally a "change in window touching the failing surface", flagged as a secondary explanation.

Classification: **DNS**, triggered by an infrastructure change to CoreDNS. The agent does not need to invent a separate "config-correlator" path because the DNS path already encodes "recent change to VPC / Route53 / CoreDNS / systemd-resolved" as a confirming signal.

## Step 4: confirm with three independent signals

1. **Logs** (`fixtures/02-dns-resolution-failure/logs.jsonl`): 47 `SERVFAIL` log lines from `inventory-svc` calling `catalog-svc.internal`, plus 8 `getaddrinfo` errors in `payments-api` (a second consumer of the same zone).
2. **Metrics** (`fixtures/02-dns-resolution-failure/metrics.json`): DNS resolver error counter elevated 12x baseline. Application error rate at `inventory-svc` climbed from 0.2% to 3.4%. Memory and CPU flat.
3. **Infra change** (`fixtures/02-dns-resolution-failure/deploys.json`): `kube-system/coredns` ConfigMap updated 15 minutes before T0, diff touches the `.internal` zone forward configuration.

A fourth signal: **traces** (`fixtures/02-dns-resolution-failure/traces.jsonl`) show failing spans with `dns.error=SERVFAIL` attribute, isolated to outbound calls to `*.internal` hostnames. Other outbound calls (e.g. to `api.stripe.com`) are unaffected. Asymmetric pattern is consistent with DNS scoped to one zone.

## Step 5: quantify blast radius

- **Users affected**: ~30% of requests that depend on `catalog-svc` fail or hit retry latency. Read-only catalog browsing degraded; checkout still works because the order-creation path does not call `catalog-svc` synchronously.
- **Surfaces affected**: all `inventory-svc` endpoints that hit `catalog-svc`, plus any other consumer of `*.internal` zones (at least `payments-api`).
- **Business impact**: catalog browsing degraded across the platform. SLO burn at 8x normal rate for read endpoints.

## Step 6: propose mitigation before root cause

1. **Revert** the `kube-system/coredns` ConfigMap to the version from `09:30:00Z`. The change is the clearly implicated single change in window, and reverting a ConfigMap takes one `kubectl apply` of the previous manifest.
2. **Feature-flag off**: not applicable. No feature flag controls DNS resolution.
3. **Scale up**: not applicable. The failure is not capacity-bound.
4. **Traffic-shift**: not applicable in this single-cluster topology. If the cluster had a sibling cluster on a different DNS configuration, shifting traffic there would be a viable stopgap.
5. **Manual intervention**: restarting CoreDNS pods does not help because they reload from the same broken ConfigMap. Restarting client pods does not help because they will hit the same resolver. Skip.

Recommended action: **revert the `kube-system/coredns` ConfigMap**.

## Step 7: hand off

```json
{
  "timeline": [
    {"t": "2026-04-08T09:32:18Z", "event": "kube-system/coredns ConfigMap updated (typo in .internal forward IP)"},
    {"t": "2026-04-08T09:34:00Z", "event": "First SERVFAIL log line from inventory-svc"},
    {"t": "2026-04-08T09:47:00Z", "event": "T0: alert inventory_svc_error_rate > 3% fires"},
    {"t": "2026-04-08T09:53:00Z", "event": "Tnow: investigation triggered"}
  ],
  "ranked_hypotheses": [
    {
      "path": "DNS (infra-change-triggered)",
      "confidence": "high",
      "evidence": ["47 SERVFAIL log lines in window", "DNS resolver error counter 12x baseline", "CoreDNS ConfigMap change 15min before T0 touches .internal zone", "outbound calls to non-.internal hosts unaffected"]
    }
  ],
  "mitigation_taken": null,
  "mitigation_recommended": "Revert kube-system/coredns ConfigMap to the 09:30:00Z version",
  "open_questions": [
    "Why did the ConfigMap change ship without a syntax-check or a staged rollout?",
    "Why is there no end-to-end DNS resolution health check on the cluster's internal zones?"
  ]
}
```

## Why this is the DNS reference path

- The failure shape is intermittent (not 100%), which is the signature DNS issues often present and which the OOM and deploy-correlator paths cannot explain.
- The change surface contains an infrastructure change rather than a code deploy, which forces the agent to widen its mental model beyond "what code shipped".
- The signal asymmetry (outbound calls to `*.internal` fail, calls to `*.com` work) is diagnostic for DNS scoped to a zone, and would be invisible without the trace-level attribute.

Skipping step 4 (three independent signals) is the most likely failure mode here: an agent that classifies on logs alone may over-attribute the failure to the consumer service rather than the resolver.
