"""
Per-fixture incident contexts and expected answers, used by run_eval.py.

The "expected_*" fields are the deterministic answers from _methodology.py
run against each fixture (see tests/replay_*.py). They are the source of
truth the judge model compares the agent's output against.

Stdlib only. No external dependencies.
"""

from __future__ import annotations

from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures"

# Each entry: a fixture-specific incident the eval will run agents against.
# Keep this list aligned with the replay_*.py files under tests/.

INCIDENTS = [
    {
        "id": "01-oom-cascade",
        "fixture_dir": FIXTURES_DIR / "01-oom-cascade",
        "service": "payments-api",
        "alert_time": "2026-03-12T14:32:00Z",
        "alert_message": "payments_api_error_rate > 5%",
        "tnow": "2026-03-12T14:36:00Z",
        "failing_surface_hints": ["webhook", "buffer"],
        "expected_t0": "2026-03-12T14:32:00Z",
        "expected_change_count": 1,
        "expected_change_summary": "deploy payments-api v4.18.0 (commit 9f3a2c1) in window",
        "expected_path": "OOM",
        "expected_top_mitigation": "revert payments-api to v4.17.4",
        "expected_escalate": False,
    },
    {
        "id": "02-dns-resolution-failure",
        "fixture_dir": FIXTURES_DIR / "02-dns-resolution-failure",
        "service": "inventory-svc",
        "alert_time": "2026-04-08T09:47:00Z",
        "alert_message": "inventory_svc_error_rate > 3%",
        "tnow": "2026-04-08T09:53:00Z",
        "failing_surface_hints": ["coredns", ".internal"],
        "expected_t0": "2026-04-08T09:47:00Z",
        "expected_change_count": 1,
        "expected_change_summary": "kube-system/coredns ConfigMap edit (typo in .internal forward)",
        "expected_path": "DNS",
        "expected_top_mitigation": "revert the kube-system/coredns ConfigMap",
        "expected_escalate": False,
    },
    {
        "id": "03-cascading-failure-retry-storm",
        "fixture_dir": FIXTURES_DIR / "03-cascading-failure-retry-storm",
        "service": "payments-api",
        "alert_time": "2026-03-20T11:08:00Z",
        "alert_message": "payments_api_latency_p99 > 1000ms",
        "tnow": "2026-03-20T11:15:00Z",
        "failing_surface_hints": [],
        "expected_t0": "2026-03-20T11:08:00Z",
        "expected_change_count": 0,
        "expected_change_summary": "zero changes in window",
        "expected_path": "cascading-failure",
        "expected_top_mitigation": "open circuit breaker on the upstream ledger-svc call path",
        "expected_escalate": False,
    },
    {
        "id": "04-deploy-correlator-serialization",
        "fixture_dir": FIXTURES_DIR / "04-deploy-correlator-serialization",
        "service": "checkout-api",
        "alert_time": "2026-02-15T13:25:00Z",
        "alert_message": "checkout_api_error_rate > 2%",
        "tnow": "2026-02-15T13:30:00Z",
        "failing_surface_hints": ["cart", "serializer"],
        "expected_t0": "2026-02-15T13:25:00Z",
        "expected_change_count": 1,
        "expected_change_summary": "deploy checkout-api v6.4.0 (commit d1c4e22)",
        "expected_path": "deploy-correlator",
        "expected_top_mitigation": "revert checkout-api to v6.3.7",
        "expected_escalate": False,
    },
    {
        "id": "05-outside-reference-paths-third-party-rate-limit",
        "fixture_dir": FIXTURES_DIR / "05-outside-reference-paths-third-party-rate-limit",
        "service": "payments-api",
        "alert_time": "2026-05-04T16:44:00Z",
        "alert_message": "payments_api_error_rate > 2%",
        "tnow": "2026-05-04T16:50:00Z",
        "failing_surface_hints": [],
        "expected_t0": "2026-05-04T16:44:00Z",
        "expected_change_count": 0,
        "expected_change_summary": "zero changes in window",
        "expected_path": "outside-reference-paths",
        "expected_top_mitigation": "escalate to a human (third-party rate limit hypothesis)",
        "expected_escalate": True,
    },
    {
        "id": "06-ambiguous-t0-slow-burn",
        "fixture_dir": FIXTURES_DIR / "06-ambiguous-t0-slow-burn",
        "service": "recommendations-api",
        "alert_time": "2026-04-19T12:15:00Z",
        "alert_message": "operator-triggered investigation: 'slow all morning'",
        "tnow": "2026-04-19T12:15:00Z",
        "failing_surface_hints": [],
        "expected_t0": "2026-04-19T09:32:14Z",
        "expected_change_count": 0,
        "expected_change_summary": "zero changes in window (causal deploy is outside window)",
        "expected_path": "OOM",
        "expected_top_mitigation": "re-run investigation with widened window before acting",
        "expected_escalate": True,
    },
    {
        "id": "07-blast-radius-asymmetric-revert",
        "fixture_dir": FIXTURES_DIR / "07-blast-radius-asymmetric-revert",
        "service": "notifications-svc",
        "alert_time": "2026-06-02T10:03:00Z",
        "alert_message": "notifications_sms_error_rate > 50%",
        "tnow": "2026-06-02T10:10:00Z",
        "failing_surface_hints": ["twilio", "sms"],
        "expected_t0": "2026-06-02T10:03:00Z",
        "expected_change_count": 1,
        "expected_change_summary": "deploy notifications-svc v8.12.0 bundle of 6 PRs",
        "expected_path": "deploy-correlator",
        "expected_top_mitigation": "revert v8.12.0 (escalation: M3 bundle of 6 changes, broader blast radius)",
        "expected_escalate": True,
    },
    {
        "id": "08-deploy-correlator-confirmation-bias",
        "fixture_dir": FIXTURES_DIR / "08-deploy-correlator-confirmation-bias",
        "service": "users-api",
        "alert_time": "2026-07-11T14:33:00Z",
        "alert_message": "users_api_error_rate > 2%",
        "tnow": "2026-07-11T14:38:00Z",
        "failing_surface_hints": ["secret", "auth", "iam"],
        "expected_t0": "2026-07-11T14:33:00Z",
        "expected_change_count": 2,
        "expected_change_summary": "deploy (innocent) + IAM change (the actual cause)",
        "expected_path": "outside-reference-paths",
        "expected_top_mitigation": "escalate; the deploy is NOT the cause; investigate IAM revert",
        "expected_escalate": True,
    },
    {
        "id": "09-zero-changes-external-cert-expiry",
        "fixture_dir": FIXTURES_DIR / "09-zero-changes-external-cert-expiry",
        "service": "webhook-receiver",
        "alert_time": "2026-08-20T03:18:00Z",
        "alert_message": "webhook_receiver_error_rate > 4%",
        "tnow": "2026-08-20T03:25:00Z",
        "failing_surface_hints": [],
        "expected_t0": "2026-08-20T03:18:00Z",
        "expected_change_count": 0,
        "expected_change_summary": "zero changes in window",
        "expected_path": "outside-reference-paths",
        "expected_top_mitigation": "escalate; external partner TLS cert expired",
        "expected_escalate": True,
    },
    {
        "id": "10-multi-region-asymmetry",
        "fixture_dir": FIXTURES_DIR / "10-multi-region-asymmetry",
        "service": "image-svc",
        "alert_time": "2026-09-14T11:42:00Z",
        "alert_message": "image_svc_error_rate > 5% (aggregate)",
        "tnow": "2026-09-14T11:50:00Z",
        "failing_surface_hints": [],
        "expected_t0": "2026-09-14T11:42:00Z",
        "expected_change_count": 0,
        "expected_change_summary": "zero changes in window; regional asymmetry us-east-1 vs us-west-2",
        "expected_path": "outside-reference-paths",
        "expected_top_mitigation": "traffic-shift to us-west-2; escalate config-drift investigation",
        "expected_escalate": True,
    },
    {
        "id": "11-capacity-bound-organic-growth",
        "fixture_dir": FIXTURES_DIR / "11-capacity-bound-organic-growth",
        "service": "search-svc",
        "alert_time": "2026-10-08T10:55:00Z",
        "alert_message": "search_svc_error_rate > 3%",
        "tnow": "2026-10-08T11:05:00Z",
        "failing_surface_hints": [],
        "expected_t0": "2026-10-08T10:55:00Z",
        "expected_change_count": 0,
        "expected_change_summary": "zero changes in window; sustained request-rate growth",
        "expected_path": "outside-reference-paths",
        "expected_top_mitigation": "scale search-svc horizontally",
        "expected_escalate": True,
    },
]


def load_fixture_text(fixture_dir: Path) -> str:
    """Concatenate the fixture files into a single text blob for prompt embedding."""
    parts = []
    for name in ("deploys.json", "pod_events.jsonl", "metrics.json", "logs.jsonl", "traces.jsonl"):
        path = fixture_dir / name
        if not path.exists():
            continue
        parts.append(f"=== {name} ===\n{path.read_text()}")
    return "\n\n".join(parts)
