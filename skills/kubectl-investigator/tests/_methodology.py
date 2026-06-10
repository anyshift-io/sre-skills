"""
Reference implementation of the kubectl-investigator methodology.

This module is a deterministic stand-in for what an AI agent does when it
follows SKILL.md. It exists so replay tests can assert that the methodology,
applied to known fixtures, produces the expected classification, mitigation,
and handoff payload.

Stdlib only. No external dependencies. No external credentials. Runs anywhere
Python 3.10+ runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

WINDOW_LEAD_IN = timedelta(minutes=15)


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _in_window(ts_iso: str, window: tuple[datetime, datetime]) -> bool:
    ts = _parse_ts(ts_iso)
    return window[0] <= ts <= window[1]


@dataclass
class Investigation:
    """Structured output of the methodology, one per incident."""

    t0: datetime
    tnow: datetime
    window: tuple[datetime, datetime]
    change_surface: list[dict[str, Any]] = field(default_factory=list)
    classified_path: str = ""
    classification_evidence: list[str] = field(default_factory=list)
    confirming_signals: list[dict[str, str]] = field(default_factory=list)
    blast_radius: dict[str, Any] = field(default_factory=dict)
    mitigation_ranked: list[dict[str, str]] = field(default_factory=list)
    handoff: dict[str, Any] = field(default_factory=dict)
    escalate_to_human: bool = False
    escalation_reasons: list[str] = field(default_factory=list)
    t0_ambiguous: bool = False
    regional_asymmetry: dict[str, Any] = field(default_factory=dict)


def load_fixture(fixture_dir: Path, name: str) -> Any:
    """Load a fixture file. .json returns parsed JSON; .jsonl returns a list."""
    path = fixture_dir / name
    if name.endswith(".jsonl"):
        with path.open() as f:
            return [json.loads(line) for line in f if line.strip()]
    with path.open() as f:
        return json.load(f)


def anchor_window(t0_iso: str, tnow_iso: str) -> tuple[datetime, datetime, tuple[datetime, datetime]]:
    """Step 1: anchor T0 and Tnow, return the [T0 - 15min, Tnow] window."""
    t0 = _parse_ts(t0_iso)
    tnow = _parse_ts(tnow_iso)
    if t0 > tnow:
        raise ValueError("T0 cannot be after Tnow")
    window = (t0 - WINDOW_LEAD_IN, tnow)
    return t0, tnow, window


def bisect_change_surface(deploys_fixture: dict, window: tuple[datetime, datetime]) -> list[dict]:
    """Step 2: pull every change event overlapping the window."""
    changes = []
    for deploy in deploys_fixture.get("deploys", []):
        if _in_window(deploy["deployed_at"], window):
            changes.append({**deploy, "kind": "deploy"})
    for change in deploys_fixture.get("infra_changes", []):
        if _in_window(change.get("changed_at", ""), window):
            changes.append({**change, "kind": "infra"})
    for change in deploys_fixture.get("rbac_changes", []):
        if _in_window(change.get("changed_at", ""), window):
            changes.append({**change, "kind": "rbac"})
    for flip in deploys_fixture.get("feature_flags", []):
        if _in_window(flip.get("flipped_at", ""), window):
            changes.append({**flip, "kind": "feature_flag"})
    for job in deploys_fixture.get("scheduled_jobs", []):
        if _in_window(job.get("ran_at", ""), window):
            changes.append({**job, "kind": "scheduled_job"})
    return changes


def _has_oom_signature(pod_events: list[dict], metrics: dict, window: tuple[datetime, datetime]) -> tuple[bool, list[str]]:
    evidence = []
    oom_events = [e for e in pod_events if e.get("reason") == "OOMKilled" and _in_window(e["t"], window)]
    if oom_events:
        evidence.append(f"{len(oom_events)} OOMKilled events on pods")
    limit = metrics.get("memory_limit_bytes", 0)
    if limit:
        peak = max((s.get("rss_bytes_p95", 0) for s in metrics.get("samples", []) if _in_window(s["t"], window)), default=0)
        if peak >= 0.9 * limit:
            evidence.append(f"RSS p95 reached {peak} bytes against limit {limit} bytes (>=90%)")
    # GC pause growth (5x baseline or higher) is a slow-burn OOM signature even without
    # an OOMKill yet. Covers the leak-trajectory case where memory hasn't quite hit the
    # limit but is heading there.
    samples_with_gc = [s for s in metrics.get("samples", []) if _in_window(s["t"], window) and "gc_pause_p99_ms" in s]
    if len(samples_with_gc) >= 2:
        baseline_gc = samples_with_gc[0]["gc_pause_p99_ms"]
        peak_gc = max(s["gc_pause_p99_ms"] for s in samples_with_gc)
        if baseline_gc > 0 and peak_gc >= 5 * baseline_gc:
            evidence.append(f"GC pause p99 grew from {baseline_gc}ms to {peak_gc}ms ({peak_gc / baseline_gc:.1f}x baseline)")
    return (len(evidence) >= 2, evidence)


def _has_dns_signature(logs: list[dict], window: tuple[datetime, datetime]) -> tuple[bool, list[str]]:
    evidence = []
    dns_error_markers = ("NXDOMAIN", "SERVFAIL", "getaddrinfo", "no such host", "dns resolution")
    matching = [log for log in logs if _in_window(log["t"], window) and any(m.lower() in log.get("msg", "").lower() for m in dns_error_markers)]
    if matching:
        evidence.append(f"{len(matching)} DNS error log lines in window")
    return (len(matching) >= 3, evidence)


def _has_cascade_signature(metrics: dict, window: tuple[datetime, datetime]) -> tuple[bool, list[str]]:
    evidence = []
    samples = [s for s in metrics.get("samples", []) if _in_window(s["t"], window)]
    if len(samples) < 2:
        return (False, evidence)
    baseline = samples[0].get("gateway_retry_rate_rps", 0)
    peak = max((s.get("gateway_retry_rate_rps", 0) for s in samples), default=0)
    if baseline > 0 and peak >= 3 * baseline:
        evidence.append(f"gateway retry rate spiked from {baseline} to {peak} rps ({peak / baseline:.1f}x baseline)")
        return (True, evidence)
    # Cascade can also surface as upstream latency growth without a retry-rate spike
    # (thread-pool saturation pattern). Detect that as a secondary check.
    upstream_p99_field = "upstream_latency_p99_ms"
    if all(upstream_p99_field in s for s in samples):
        baseline_lat = samples[0][upstream_p99_field]
        peak_lat = max(s[upstream_p99_field] for s in samples)
        if baseline_lat > 0 and peak_lat >= 3 * baseline_lat:
            evidence.append(f"upstream P99 latency grew from {baseline_lat}ms to {peak_lat}ms ({peak_lat / baseline_lat:.1f}x baseline)")
            return (True, evidence)
    return (False, evidence)


def _detect_regional_asymmetry(metrics: dict, window: tuple[datetime, datetime]) -> dict[str, Any]:
    """Detect per-region asymmetry in error rate. Empty dict if no region field in fixtures."""
    samples = [s for s in metrics.get("samples", []) if _in_window(s["t"], window) and "region" in s]
    if not samples:
        return {}
    regions: dict[str, list[float]] = {}
    for s in samples:
        regions.setdefault(s["region"], []).append(s.get("error_rate_pct", 0))
    if len(regions) < 2:
        return {}
    region_max = {r: max(vals) for r, vals in regions.items()}
    worst = max(region_max.values())
    best = min(region_max.values())
    if worst >= 5 * max(best, 0.5):
        return {
            "detected": True,
            "per_region_peak_error_rate_pct": region_max,
            "asymmetry_ratio": round(worst / max(best, 0.5), 1),
        }
    return {"detected": False, "per_region_peak_error_rate_pct": region_max}


def _deploy_correlator_evidence(changes: list[dict], failing_surface_hints: list[str]) -> list[str]:
    evidence = []
    for change in changes:
        if change["kind"] != "deploy":
            continue
        diff = change.get("diff_summary", "").lower()
        for hint in failing_surface_hints:
            if hint.lower() in diff:
                evidence.append(f"deploy {change.get('version', '?')} ({change.get('commit', '?')}) touches failing surface: {hint}")
                break
    return evidence


def classify(
    pod_events: list[dict],
    metrics: dict,
    logs: list[dict],
    changes: list[dict],
    window: tuple[datetime, datetime],
    failing_surface_hints: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Step 3: classify against the four reference paths.

    Returns (path, evidence_lines). Path is one of:
    "OOM", "DNS", "cascading-failure", "deploy-correlator", "outside-reference-paths".

    When OOM is triggered by a deploy, returns "OOM" (the OOM is the root path; the
    deploy explains the trigger but the failure shape is OOM). Reflected in the
    SKILL.md guidance: classify the primary path, note the cascade or trigger as
    second-order, do not collapse into a single label.
    """
    failing_surface_hints = failing_surface_hints or []

    oom_hit, oom_evidence = _has_oom_signature(pod_events, metrics, window)
    dns_hit, dns_evidence = _has_dns_signature(logs, window)
    cascade_hit, cascade_evidence = _has_cascade_signature(metrics, window)
    deploy_evidence = _deploy_correlator_evidence(changes, failing_surface_hints)

    if oom_hit:
        evidence = oom_evidence + deploy_evidence + cascade_evidence
        return ("OOM", evidence)
    if dns_hit:
        evidence = dns_evidence + deploy_evidence
        return ("DNS", evidence)
    if cascade_hit and not oom_hit and not dns_hit:
        return ("cascading-failure", cascade_evidence)
    if deploy_evidence and not cascade_hit:
        return ("deploy-correlator", deploy_evidence)
    return ("outside-reference-paths", ["no reference-path signature met threshold"])


def confirm_signals(
    pod_events: list[dict],
    metrics: dict,
    logs: list[dict],
    changes: list[dict],
    traces: list[dict],
    window: tuple[datetime, datetime],
) -> list[dict[str, str]]:
    """Step 4: list signals supporting the hypothesis, drawn from independent sources.

    Each source contributes at most one entry; this enforces the "two signals from the
    same source count as one" rule from SKILL.md step 4.
    """
    signals: list[dict[str, str]] = []

    # orchestrator_events source
    oom_events = [e for e in pod_events if e.get("reason") == "OOMKilled" and _in_window(e["t"], window)]
    if oom_events:
        signals.append({"source": "orchestrator_events", "evidence": f"{len(oom_events)} OOMKilled pod events in window"})

    # metrics source: any of memory-at-limit, upstream-latency growth, retry-rate spike, error-rate jump.
    samples = [s for s in metrics.get("samples", []) if _in_window(s["t"], window)]
    if samples:
        metric_evidence_parts = []
        limit = metrics.get("memory_limit_bytes", 0)
        peak_rss = max((s.get("rss_bytes_p95", 0) for s in samples), default=0)
        if limit and peak_rss >= 0.9 * limit:
            metric_evidence_parts.append(f"RSS p95 peak {peak_rss}B vs limit {limit}B")
        if all("upstream_latency_p99_ms" in s for s in samples):
            up_baseline = samples[0]["upstream_latency_p99_ms"]
            up_peak = max(s["upstream_latency_p99_ms"] for s in samples)
            if up_baseline > 0 and up_peak >= 3 * up_baseline:
                metric_evidence_parts.append(f"upstream P99 latency {up_baseline}ms -> {up_peak}ms ({up_peak / up_baseline:.1f}x)")
        retry_baseline = samples[0].get("gateway_retry_rate_rps", 0)
        retry_peak = max((s.get("gateway_retry_rate_rps", 0) for s in samples), default=0)
        if retry_baseline > 0 and retry_peak >= 3 * retry_baseline:
            metric_evidence_parts.append(f"gateway retry rate {retry_baseline} -> {retry_peak} rps ({retry_peak / retry_baseline:.1f}x)")
        err_baseline = samples[0].get("error_rate_pct", 0)
        err_peak = max(s.get("error_rate_pct", 0) for s in samples)
        if err_peak >= max(1.0, 3 * err_baseline):
            metric_evidence_parts.append(f"error rate {err_baseline}% -> {err_peak}%")
        if metric_evidence_parts:
            signals.append({"source": "metrics", "evidence": "; ".join(metric_evidence_parts)})

    # change_audit / deploy_diff sources
    deploy_changes = [c for c in changes if c["kind"] == "deploy"]
    if deploy_changes:
        signals.append({"source": "deploy_diff", "evidence": f"deploy {deploy_changes[0].get('version', '?')} in window: {deploy_changes[0].get('diff_summary', '')[:120]}"})
    non_deploy_changes = [c for c in changes if c["kind"] != "deploy"]
    if non_deploy_changes:
        first = non_deploy_changes[0]
        descriptor = first.get("resource") or first.get("flag") or first.get("job") or first["kind"]
        signals.append({"source": "change_audit", "evidence": f"{first['kind']} change in window: {descriptor} - {first.get('diff_summary', '')[:120]}"})

    # traces source
    fail_traces = [t for t in traces if _in_window(t["t"], window) and t.get("outcome") == "fail"]
    if fail_traces:
        signals.append({"source": "traces", "evidence": f"{len(fail_traces)} failing distributed traces in window"})

    # logs source: DNS errors, timeout errors, thread-pool saturation, OOM logs.
    log_markers = (
        "NXDOMAIN", "SERVFAIL", "getaddrinfo", "no such host",
        "timeout", "thread pool saturated", "out of memory",
        "retry budget exhausted",
    )
    log_hits = [log for log in logs if _in_window(log["t"], window) and any(m.lower() in log.get("msg", "").lower() for m in log_markers)]
    if log_hits:
        signals.append({"source": "logs", "evidence": f"{len(log_hits)} error log lines in window (timeout / saturation / DNS / OOM patterns)"})

    return signals


def blast_radius(metrics: dict, window: tuple[datetime, datetime]) -> dict[str, Any]:
    """Step 5: quantify users / surfaces / business impact from telemetry."""
    samples = [s for s in metrics.get("samples", []) if _in_window(s["t"], window)]
    if not samples:
        return {"users_affected_pct": None, "request_rate_peak": None, "error_rate_peak_pct": None, "request_rate_growing": False}
    rates = [s.get("request_rate_rps", 0) for s in samples]
    request_rate_growing = False
    if len(rates) >= 3 and rates[0] > 0:
        request_rate_growing = rates[-1] >= 1.5 * rates[0]
    return {
        "users_affected_pct": max(s.get("error_rate_pct", 0) for s in samples),
        "request_rate_peak": max(rates),
        "error_rate_peak_pct": max(s.get("error_rate_pct", 0) for s in samples),
        "request_rate_growing": request_rate_growing,
    }


def propose_mitigation(
    classified_path: str,
    changes: list[dict],
    blast: dict[str, Any],
) -> list[dict[str, str]]:
    """Step 6: ordered mitigation list. Mitigation before root cause."""
    actions: list[dict[str, str]] = []
    # Revert the implicated change. Prefer reverting the change in window (code deploy,
    # cluster/config change, RBAC change, or feature flag flip), whichever is the implicated
    # single change. Methodology rule: mitigation before root cause.
    revertable = [c for c in changes if c["kind"] in ("deploy", "infra", "rbac", "feature_flag")]
    if revertable and classified_path in ("OOM", "deploy-correlator", "cascading-failure", "DNS"):
        change = revertable[0]
        if change["kind"] == "deploy":
            target = f"{change.get('service', '?')} to previous version"
            note = f"deploy {change.get('version', '?')} ({change.get('commit', '?')}) is in window and touches the failing surface"
        elif change["kind"] == "infra":
            target = f"{change.get('resource', '?')} to pre-{change.get('changed_at', '?')} state"
            note = f"cluster/infra change to {change.get('resource', '?')} is in window and touches the failing surface"
        elif change["kind"] == "rbac":
            target = f"{change.get('resource', '?')} RBAC change"
            note = f"RBAC change to {change.get('resource', '?')} is in window and touches the failing surface"
        else:  # feature_flag
            target = f"{change.get('flag', '?')} feature flag"
            note = f"feature flag {change.get('flag', '?')} was flipped in window"
        actions.append({"action": "revert", "target": target, "note": note})
    # Pure cascade with no in-window change: circuit-breaker / traffic-shift come first.
    if classified_path == "cascading-failure" and not revertable:
        actions.append({
            "action": "circuit_breaker",
            "target": "open circuit on the degraded upstream dependency",
            "note": "stops the retry storm from amplifying the underlying degradation. Does not fix the upstream itself.",
        })
        actions.append({
            "action": "traffic_shift",
            "target": "shed traffic from the saturating service or shift to a healthy replica",
            "note": "buys time while the upstream recovers or is scaled.",
        })
    if classified_path == "OOM":
        actions.append({
            "action": "scale_resource",
            "target": "memory limit",
            "note": "stopgap if revert is delayed. Does not address cause. Will increase per-pod cost.",
        })
    if classified_path == "DNS":
        actions.append({
            "action": "traffic_shift",
            "target": "regions / resolvers not affected by DNS issue",
            "note": "if asymmetric. Verify the unaffected path actually bypasses the broken resolver before shifting traffic.",
        })
    # Outside reference paths with sustained traffic growth: scaling is a valid first action.
    if classified_path == "outside-reference-paths" and blast.get("request_rate_growing"):
        actions.append({
            "action": "scale_resource",
            "target": "horizontal scale of the saturated service",
            "note": "request rate has been climbing across the window and headroom is exhausted. Scaling addresses the immediate cause; capacity planning addresses the root cause.",
        })
    actions.append({
        "action": "manual_intervention",
        "target": "restart affected pods / processes",
        "note": "last resort. Does not address cause. Failure will recur.",
    })
    return actions


def maybe_escalate(
    classified_path: str,
    changes: list[dict],
    signals: list[dict[str, str]],
    blast: dict[str, Any],
    t0_ambiguous: bool = False,
    regional_asymmetry: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """Aggregate the FAILURE_MODES.md escalation rules.

    Implemented checks: M1 (outside reference paths), M2 (ambiguous T0),
    M3 (revert blast-radius exceeds incident), the M-bias three-independent-signals
    guard, and the regional-asymmetry surfacing as a soft signal. M4 (deploy-correlator
    confirmation bias) is handled structurally by classify(), which requires
    diff-touches-failing-surface evidence before classifying as deploy-correlator;
    a timing-only correlation falls through to outside-reference-paths and trips M1.
    The operational rules (O1 missing sources, O2 telemetry blackout, O3 multi-incident)
    are surfaced as fixture-schema follow-ups.
    """
    reasons = []
    if classified_path == "outside-reference-paths":
        reasons.append("M1: failure classified outside the four reference paths")
    if len({s["source"] for s in signals}) < 3:
        reasons.append("M-bias: fewer than three independent signal sources")
    if t0_ambiguous:
        reasons.append("M2: T0 is ambiguous; re-run with a widened window before acting on the recommended mitigation")
    # M3: revert blast radius vs incident blast radius.
    revertable = [c for c in changes if c["kind"] in ("deploy", "infra", "rbac", "feature_flag")]
    if revertable and classified_path in ("OOM", "deploy-correlator", "cascading-failure", "DNS"):
        change = revertable[0]
        bundle_size = change.get("bundle_size", 1)
        if bundle_size > 1:
            reasons.append(
                f"M3: recommended revert affects {bundle_size} bundled changes, broader blast radius than the incident; requires a human approver before executing"
            )
    if regional_asymmetry and regional_asymmetry.get("detected"):
        reasons.append(
            f"regional-asymmetry: per-region error-rate peaks {regional_asymmetry.get('per_region_peak_error_rate_pct')}; treat as a config-drift hypothesis and escalate"
        )
    return (len(reasons) > 0, reasons)


def handoff_payload(investigation: Investigation) -> dict[str, Any]:
    """Step 7: structured handoff for postmortem-author."""
    return {
        "t0": investigation.t0.isoformat(),
        "t0_ambiguous": investigation.t0_ambiguous,
        "tnow": investigation.tnow.isoformat(),
        "classified_path": investigation.classified_path,
        "evidence": investigation.classification_evidence,
        "confirming_signals": investigation.confirming_signals,
        "blast_radius": investigation.blast_radius,
        "regional_asymmetry": investigation.regional_asymmetry,
        "mitigation_recommended": investigation.mitigation_ranked[0] if investigation.mitigation_ranked else None,
        "mitigation_alternatives": investigation.mitigation_ranked[1:],
        "escalate_to_human": investigation.escalate_to_human,
        "escalation_reasons": investigation.escalation_reasons,
    }


def run_investigation(
    fixture_dir: Path,
    t0_iso: str,
    tnow_iso: str,
    failing_surface_hints: list[str] | None = None,
    t0_ambiguous: bool = False,
) -> Investigation:
    """End-to-end: load fixtures, run steps 1-7, return the structured investigation."""
    deploys = load_fixture(fixture_dir, "deploys.json")
    pod_events = load_fixture(fixture_dir, "pod_events.jsonl") if (fixture_dir / "pod_events.jsonl").exists() else []
    metrics = load_fixture(fixture_dir, "metrics.json")
    logs = load_fixture(fixture_dir, "logs.jsonl") if (fixture_dir / "logs.jsonl").exists() else []
    traces = load_fixture(fixture_dir, "traces.jsonl") if (fixture_dir / "traces.jsonl").exists() else []

    t0, tnow, window = anchor_window(t0_iso, tnow_iso)
    changes = bisect_change_surface(deploys, window)
    path, evidence = classify(pod_events, metrics, logs, changes, window, failing_surface_hints)
    signals = confirm_signals(pod_events, metrics, logs, changes, traces, window)
    blast = blast_radius(metrics, window)
    regional = _detect_regional_asymmetry(metrics, window)
    mitigation = propose_mitigation(path, changes, blast)
    escalate, escalation_reasons = maybe_escalate(path, changes, signals, blast, t0_ambiguous=t0_ambiguous, regional_asymmetry=regional)

    investigation = Investigation(
        t0=t0,
        tnow=tnow,
        window=window,
        change_surface=changes,
        classified_path=path,
        classification_evidence=evidence,
        confirming_signals=signals,
        blast_radius=blast,
        mitigation_ranked=mitigation,
        escalate_to_human=escalate,
        escalation_reasons=escalation_reasons,
        t0_ambiguous=t0_ambiguous,
        regional_asymmetry=regional,
    )
    investigation.handoff = handoff_payload(investigation)
    return investigation
