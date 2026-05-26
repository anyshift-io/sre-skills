# Worked example 9: zero changes in window (external TLS certificate expiry)

A failure where the change-surface bisection returns empty and the actual cause is external: a partner's TLS certificate expired. Tests the methodology's pivot from "find the change" to "consider external causes" when step 2 returns zero. Fixtures and replay test under `../fixtures/09-zero-changes-external-cert-expiry/` and `../tests/replay_09_cert_expiry.py`.

## Scenario

- **Service**: `webhook-receiver` calls `partner.example.com` to register webhook subscriptions.
- **Failure**: at 2026-08-20 03:00 UTC, the partner's TLS certificate expired. Outbound calls now fail with `tls: certificate has expired`. The partner has not yet rotated the cert.
- **Alert at 03:18 UTC**: `webhook_receiver_error_rate > 4%`.
- **No changes anywhere on our side**. The cert expiry happens at midnight UTC for whatever timezone the partner is in, with no announcement.
- **Methodology must produce**: classification `outside-reference-paths`, the change-surface bisection should return zero, and the methodology should surface the "zero changes → external cause" pivot in its reasoning. Escalation with M1.

## Step 1: anchor the window

- **T0**: `2026-08-20T03:18:00Z` (alert fire).
- **Tnow**: `2026-08-20T03:25:00Z`.
- **Window**: `[03:03:00Z, 03:25:00Z]`.

## Step 2: bisect the change surface

| Source | Event | Time | Detail |
|---|---|---|---|
| CI/CD | (none) | | |
| Terraform | (none) | | |
| IAM | (none) | | |
| Feature flags | (none) | | |
| Cron / batch | (none) | | |

**Zero changes in window.** Per SKILL.md step 2: "treat as a strong signal in itself: the failure is likely external (upstream provider, certificate expiry, DNS, capacity drift) rather than a self-inflicted regression."

The methodology must explicitly enumerate this and pivot to external-cause hypotheses for step 3.

## Step 3: classify against the four reference paths

- **OOM**: RSS p95 flat. No `OOMKilled`. No match.
- **DNS**: `partner.example.com` resolves successfully (`dns_target` attribute on traces shows valid IPs). The handshake fails *after* DNS, not at DNS. No DNS-classification match.
- **Cascading-failure**: no internal upstream-latency growth, no retry-storm signature beyond a modest retry-budget increase. No match.
- **Deploy-correlator**: no deploy. No match.

Classification: **outside-reference-paths**. The failure shape (TLS handshake error, `certificate has expired` in error message) points to a third-party cert issue.

## Step 4: confirm with three independent signals

1. **Logs**: `tls: certificate has expired` errors from `webhook-receiver` calling `partner.example.com`, starting 03:01:14Z (just after midnight UTC).
2. **Traces**: failing spans terminate at the `webhook-receiver` → `partner` hop with `tls.error=certificate_expired`. The `dns_target` attribute resolves successfully; the failure is post-DNS.
3. **Metrics**: error rate climbs from 0.2% baseline to 6.8% as queued webhook deliveries fail; internal RSS flat; DNS resolver error counter flat.

Three independent signal sources. Hypothesis (external partner cert expiry) is high-confidence on the evidence even though the classification is outside-paths.

## Step 5: quantify blast radius

- **Users affected**: every webhook subscription update to this partner. New subscriptions queue; existing connections to other partners work fine.
- **Surfaces affected**: only the partner-specific webhook path.
- **Business impact**: integration with this partner degraded. Other partners unaffected.

## Step 6: propose mitigation before root cause

Outside-paths classification means the methodology constrains the mitigation set:

1. **Revert**: not applicable; no change to revert.
2. **Feature-flag off** the partner integration if a flag exists, surfacing a "partner integration paused" message to users. Allowed without escalation.
3. **Traffic-shift** to a redundant partner endpoint if one is configured. Verify the endpoint actually bypasses the expired cert.
4. **Scale**: not applicable.
5. **Manual intervention**: not applicable.

The actual remediation requires the *partner* to rotate the cert. We can only escalate and pause the integration on our side.

Recommended next action: **escalate to a human with the cert-expiry hypothesis and the partner's incident contact details**.

## Step 7: hand off

```json
{
  "timeline": [
    {"t": "2026-08-20T03:01:14Z", "event": "First tls: certificate has expired error from partner.example.com"},
    {"t": "2026-08-20T03:18:00Z", "event": "T0: alert webhook_receiver_error_rate > 4% fires"},
    {"t": "2026-08-20T03:25:00Z", "event": "Tnow: investigation triggered"}
  ],
  "ranked_hypotheses": [
    {
      "path": "External: partner TLS certificate expired (outside reference paths)",
      "confidence": "high (on hypothesis), classified as outside-reference-paths",
      "evidence": ["tls: certificate has expired in logs", "TLS error post-DNS in traces", "zero changes on our side in window", "partner.example.com is the consistent failing target"]
    }
  ],
  "mitigation_taken": null,
  "mitigation_recommended": "Escalate. Pause partner integration via feature flag if available. Contact partner's incident channel for cert rotation ETA.",
  "escalate_to_human": true,
  "escalation_reasons": ["M1: failure classified outside the four reference paths"],
  "open_questions": [
    "Does the partner have a cert-monitoring SLA they violated?",
    "Should we monitor partner cert expiry proactively (out-of-band check that warns 14 days before expiry)?",
    "Do we have a redundant partner endpoint with an independent cert chain?"
  ]
}
```

## Why this is the zero-changes reference example

- It validates SKILL.md step 2's claim that "zero changes is itself a strong signal." Without that pivot, an agent that always hunts for an internal cause would waste investigation time and possibly invent a phantom hypothesis.
- It separates *DNS path* from *TLS issue*: both involve failing outbound calls, but the diagnostic shape is different (DNS fails at resolution; TLS fails after resolution). The example exercises the methodology's discipline on this distinction.
- It models the case where remediation is fundamentally *out of our control*. The methodology's job in that case is to surface a clear hypothesis and stop, not to invent action.
