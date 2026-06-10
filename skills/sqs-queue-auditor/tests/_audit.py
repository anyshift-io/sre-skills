"""
Reference implementation of the sqs-queue-auditor methodology.

This module is a deterministic stand-in for what an AI agent does when it
follows SKILL.md. It exists so replay tests can assert that the methodology,
applied to known `GetQueueAttributes` fixtures, produces the expected findings
and the expected boundary (the questions the queue config alone cannot answer).

Input shape mirrors the real AWS SQS API: `GetQueueAttributes` returns every
attribute as a string, and the compound attributes (`RedrivePolicy`, `Policy`,
`RedriveAllowPolicy`) are JSON documents encoded *inside* those strings. Parsing
that correctly is part of the judgment this skill encodes: a naive read treats
`MessageRetentionPeriod` as already-numeric and never opens the embedded
RedrivePolicy at all.

Stdlib only. No external dependencies. No external credentials. Runs anywhere
Python 3.10+ runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# AWS defaults and limits (seconds).
DEFAULT_VISIBILITY_TIMEOUT = 30
DEFAULT_RETENTION = 345_600          # 4 days, the SQS default
MAX_RETENTION = 1_209_600            # 14 days, the SQS maximum
SHORT_RETENTION_THRESHOLD = 3_600    # below 1h, a brief consumer outage loses data

# maxReceiveCount sane band. Below: a single transient failure dead-letters good
# messages. Above: poison messages are retried many times before quarantine, which
# delays detection and (with a large visibility timeout) feeds the R4 age-out bug.
MAXRECEIVE_MIN_SANE = 3
MAXRECEIVE_MAX_SANE = 10

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# Condition keys that narrow an otherwise-open principal to something legitimate
# (a specific source service, account, or org). Their presence turns a `Principal:*`
# statement from "the public internet" into "this SNS topic / this account".
_NARROWING_CONDITION_KEYS = (
    "aws:SourceArn",
    "aws:SourceAccount",
    "aws:PrincipalOrgID",
    "aws:PrincipalAccount",
    "aws:SourceOwner",
)


@dataclass
class Finding:
    """One queue-side misconfiguration, derived from the static attributes alone."""

    code: str          # R1..R9
    severity: str      # critical | high | medium | low
    attribute: str     # the attribute(s) the finding is grounded in
    title: str
    detail: str
    recommendation: str


@dataclass
class Audit:
    """Structured output of the methodology, one per queue."""

    queue_arn: str
    is_fifo: bool = False
    has_dlq: bool = False
    findings: list[Finding] = field(default_factory=list)
    # The wall: questions a single queue's config cannot answer. Each item names a
    # join (across resources, across sources, or across time) the audit cannot make.
    boundary: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return len(self.findings) == 0

    @property
    def top_severity(self) -> str | None:
        if not self.findings:
            return None
        return min(self.findings, key=lambda f: _SEVERITY_RANK[f.severity]).severity

    def codes(self) -> set[str]:
        return {f.code for f in self.findings}


def load_attributes(path: Path) -> dict[str, str]:
    """Load a GetQueueAttributes fixture. Returns the `Attributes` string map."""
    with path.open() as f:
        doc = json.load(f)
    # Accept either the raw API envelope ({"Attributes": {...}}) or a bare map.
    return doc.get("Attributes", doc)


def _int(attrs: dict[str, str], key: str, default: int | None = None) -> int | None:
    """SQS returns every attribute as a string. Parse one as an int."""
    raw = attrs.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _json_attr(attrs: dict[str, str], key: str) -> Any:
    """Parse a compound attribute whose value is a JSON document encoded as a string."""
    raw = attrs.get(key)
    if not raw:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def parse_redrive_policy(attrs: dict[str, str]) -> tuple[str | None, int | None]:
    """Return (deadLetterTargetArn, maxReceiveCount) from the RedrivePolicy, or (None, None)."""
    policy = _json_attr(attrs, "RedrivePolicy")
    if not isinstance(policy, dict):
        return (None, None)
    arn = policy.get("deadLetterTargetArn")
    raw_count = policy.get("maxReceiveCount")
    try:
        count = int(raw_count) if raw_count is not None else None
    except (TypeError, ValueError):
        count = None
    return (arn, count)


def _principal_is_wildcard(principal: Any) -> bool:
    """True if the statement principal includes the `*` wildcard (anyone)."""
    if principal == "*":
        return True
    if isinstance(principal, dict):
        for value in principal.values():
            if value == "*":
                return True
            if isinstance(value, list) and "*" in value:
                return True
    return False


def _statement_is_narrowed(statement: dict) -> bool:
    """True if a Condition block scopes the statement to a specific source/account/org."""
    condition = statement.get("Condition")
    if not isinstance(condition, dict):
        return False
    for operator_block in condition.values():
        if not isinstance(operator_block, dict):
            continue
        for key in operator_block:
            if key in _NARROWING_CONDITION_KEYS:
                return True
    return False


# --- The checks. Each maps to one rule code documented in SKILL.md / FAILURE_MODES.md. ---


def check_redrive_wiring(
    attrs: dict[str, str],
    dlq_attrs: dict[str, str] | None,
    is_processing_queue: bool,
) -> tuple[list[Finding], bool]:
    """R1 (no DLQ), R2 (maxReceiveCount band), R3 (DLQ retention ordering)."""
    findings: list[Finding] = []
    dlq_arn, max_receive = parse_redrive_policy(attrs)
    has_dlq = dlq_arn is not None

    if not has_dlq:
        if is_processing_queue:
            findings.append(Finding(
                code="R1",
                severity="high",
                attribute="RedrivePolicy",
                title="No dead-letter queue on a processing queue",
                detail=(
                    "The queue has no RedrivePolicy. A message the consumer can never "
                    "process (a poison message) is received, fails, becomes visible "
                    "again, and is retried until MessageRetentionPeriod expires, at which "
                    "point SQS deletes it silently. There is no quarantine and no signal: "
                    "the message is simply gone, and the only evidence is a consumer that "
                    "burned cycles on it for the whole retention window."
                ),
                recommendation=(
                    "Attach a RedrivePolicy pointing at a dead-letter queue with a "
                    "maxReceiveCount in the 3-10 band, so poison messages are quarantined "
                    "for inspection instead of dropped."
                ),
            ))
        return (findings, has_dlq)

    # DLQ is present: validate maxReceiveCount and retention ordering.
    if max_receive is not None:
        if max_receive < MAXRECEIVE_MIN_SANE:
            findings.append(Finding(
                code="R2",
                severity="medium",
                attribute="RedrivePolicy.maxReceiveCount",
                title=f"maxReceiveCount is {max_receive}: transient failures dead-letter good messages",
                detail=(
                    f"With maxReceiveCount={max_receive}, a message that fails "
                    f"{max_receive} delivery attempt(s) goes to the DLQ. A brief, "
                    "recoverable downstream blip (a rolling deploy, a 2-second timeout) "
                    "is enough to send a perfectly good message to the dead-letter queue, "
                    "where it sits unprocessed. The DLQ fills with messages that were never "
                    "poison, masking the ones that are."
                ),
                recommendation="Raise maxReceiveCount into the 3-10 band so transient failures are retried before quarantine.",
            ))
        elif max_receive > MAXRECEIVE_MAX_SANE:
            findings.append(Finding(
                code="R2",
                severity="low",
                attribute="RedrivePolicy.maxReceiveCount",
                title=f"maxReceiveCount is {max_receive}: poison messages are retried before quarantine",
                detail=(
                    f"maxReceiveCount={max_receive} means a poison message is delivered "
                    f"up to {max_receive} times before reaching the DLQ. Detection of a "
                    "genuinely broken message is delayed by that many cycles, and consumer "
                    "capacity is spent reprocessing it each time. Combined with a long "
                    "visibility timeout this also feeds the age-out failure (R4)."
                ),
                recommendation="Lower maxReceiveCount into the 3-10 band unless a specific replay requirement justifies more.",
            ))

    if dlq_attrs is not None:
        source_retention = _int(attrs, "MessageRetentionPeriod", DEFAULT_RETENTION) or DEFAULT_RETENTION
        dlq_retention = _int(dlq_attrs, "MessageRetentionPeriod", DEFAULT_RETENTION) or DEFAULT_RETENTION
        if dlq_retention <= source_retention:
            findings.append(Finding(
                code="R3",
                severity="critical",
                attribute="MessageRetentionPeriod (source vs DLQ)",
                title="DLQ retention is not longer than the source: redriven messages can be deleted on arrival",
                detail=(
                    f"Source MessageRetentionPeriod is {source_retention}s; the DLQ's is "
                    f"{dlq_retention}s. A message's age is measured from its original "
                    "SentTimestamp, and SQS does not reset that timestamp when the message "
                    "is moved to the DLQ. A message that fails late in the source queue's "
                    "retention window therefore arrives in the DLQ already near (or past) "
                    f"the DLQ's {dlq_retention}s limit, and is deleted almost immediately. "
                    "The dead-letter queue looks correctly wired, yet the messages you most "
                    "need to inspect are the ones it silently drops."
                ),
                recommendation=(
                    f"Set the DLQ's MessageRetentionPeriod above the source's, ideally to "
                    f"the maximum ({MAX_RETENTION}s / 14 days), so failed messages survive "
                    "long enough to investigate and redrive."
                ),
            ))

    return (findings, has_dlq)


def check_lifecycle_timing(attrs: dict[str, str]) -> list[Finding]:
    """R4 (poison ages out before DLQ), R5 (default visibility timeout), R6 (short retention)."""
    findings: list[Finding] = []
    visibility = _int(attrs, "VisibilityTimeout", DEFAULT_VISIBILITY_TIMEOUT) or DEFAULT_VISIBILITY_TIMEOUT
    retention = _int(attrs, "MessageRetentionPeriod", DEFAULT_RETENTION) or DEFAULT_RETENTION
    _, max_receive = parse_redrive_policy(attrs)

    # R4: worst-case time for a poison message to exhaust its receive count.
    # Each failed delivery holds the message invisible for `visibility` seconds, so a
    # message needs at least maxReceiveCount * visibility seconds of wall-clock to reach
    # the DLQ. If that exceeds retention, the message ages out and is deleted *before*
    # it ever dead-letters: the DLQ is configured but unreachable for slow failures.
    if max_receive is not None and max_receive > 0:
        worst_case = max_receive * visibility
        if worst_case > retention:
            findings.append(Finding(
                code="R4",
                severity="critical",
                attribute="VisibilityTimeout x maxReceiveCount vs MessageRetentionPeriod",
                title="Poison messages age out of the source queue before reaching the DLQ",
                detail=(
                    f"maxReceiveCount={max_receive} and VisibilityTimeout={visibility}s "
                    f"means a poison message needs at least {worst_case}s to exhaust its "
                    f"receive count, but MessageRetentionPeriod is only {retention}s. "
                    "Retention wins: the message is deleted by age before it is ever moved "
                    "to the dead-letter queue. The DLQ exists and looks correct, yet the "
                    "exact messages it was built to catch never arrive in it."
                ),
                recommendation=(
                    "Lower maxReceiveCount or VisibilityTimeout (or raise "
                    "MessageRetentionPeriod) so that maxReceiveCount x VisibilityTimeout "
                    "stays well under the retention window."
                ),
            ))

    # R5: visibility timeout left at the 30s default. This is a risk flag, not a proven
    # bug: whether 30s is too short depends on consumer processing time, which is not a
    # queue attribute (see boundary). Surfaced as low severity for that reason.
    if visibility == DEFAULT_VISIBILITY_TIMEOUT:
        findings.append(Finding(
            code="R5",
            severity="low",
            attribute="VisibilityTimeout",
            title="VisibilityTimeout is at the 30s default",
            detail=(
                "VisibilityTimeout is 30s, the AWS default, which is frequently left "
                "unchanged rather than chosen. If any consumer takes longer than 30s to "
                "process a message, the message becomes visible again mid-processing and "
                "is delivered to a second consumer, causing duplicate work. Whether that "
                "actually happens depends on consumer processing time, which this audit "
                "cannot see (see boundary): this is a flag to verify, not a confirmed bug."
            ),
            recommendation="Set VisibilityTimeout deliberately, sized above the consumer's p99 processing time (commonly 6x a Lambda timeout).",
        ))

    # R6: retention so short a brief outage loses data.
    if retention < SHORT_RETENTION_THRESHOLD:
        findings.append(Finding(
            code="R6",
            severity="medium",
            attribute="MessageRetentionPeriod",
            title=f"MessageRetentionPeriod is {retention}s: a short consumer outage loses messages",
            detail=(
                f"Messages are deleted after {retention}s whether or not they were "
                "processed. A consumer outage, a deploy, or a scaling lag longer than "
                f"{retention}s silently drops every message still in the queue. The "
                "default is 4 days for a reason: it absorbs ordinary operational gaps."
            ),
            recommendation="Raise MessageRetentionPeriod to cover the longest plausible consumer outage, typically at least the 4-day default.",
        ))

    return findings


def check_exposure(attrs: dict[str, str]) -> list[Finding]:
    """R7 (open resource policy), R8 (encryption at rest disabled)."""
    findings: list[Finding] = []

    policy = _json_attr(attrs, "Policy")
    if isinstance(policy, dict):
        statements = policy.get("Statement", [])
        if isinstance(statements, dict):
            statements = [statements]
        for stmt in statements:
            if not isinstance(stmt, dict):
                continue
            if stmt.get("Effect") != "Allow":
                continue
            if _principal_is_wildcard(stmt.get("Principal")) and not _statement_is_narrowed(stmt):
                findings.append(Finding(
                    code="R7",
                    severity="high",
                    attribute="Policy",
                    title="Queue resource policy allows a wildcard principal with no narrowing condition",
                    detail=(
                        "A statement grants access to Principal \"*\" with no "
                        "aws:SourceArn / aws:SourceAccount / aws:PrincipalOrgID condition. "
                        "As written, the resource policy authorises any AWS principal to act "
                        "on this queue. This is the classic confused-deputy and public-queue "
                        "exposure: a service that should only accept messages from one SNS "
                        "topic accepts them from anyone."
                    ),
                    recommendation=(
                        "Add a Condition that pins the principal to the intended source "
                        "(aws:SourceArn for an SNS topic / S3 bucket, or aws:SourceAccount "
                        "/ aws:PrincipalOrgID for an account or org), or name explicit "
                        "principal ARNs instead of \"*\"."
                    ),
                ))
                break  # one R7 per queue is enough

    sse_managed = (attrs.get("SqsManagedSseEnabled", "false") or "false").lower() == "true"
    has_kms = bool(attrs.get("KmsMasterKeyId"))
    if not sse_managed and not has_kms:
        findings.append(Finding(
            code="R8",
            severity="low",
            attribute="SqsManagedSseEnabled / KmsMasterKeyId",
            title="Server-side encryption at rest is disabled",
            detail=(
                "Neither SQS-managed SSE nor a KMS key is configured, so message bodies "
                "are not encrypted at rest. Whether that matters depends on what the queue "
                "carries, which this audit cannot determine (see boundary): flagged as a "
                "low-severity default worth confirming against the data classification."
            ),
            recommendation="Enable SQS-managed SSE (SqsManagedSseEnabled) or a KMS key unless the data is confirmed non-sensitive.",
        ))

    return findings


def check_fifo_invariants(attrs: dict[str, str]) -> list[Finding]:
    """R9 (FIFO deduplication requires producer cooperation when content-based dedup is off)."""
    findings: list[Finding] = []
    is_fifo = (attrs.get("FifoQueue", "false") or "false").lower() == "true"
    if not is_fifo:
        return findings
    content_dedup = (attrs.get("ContentBasedDeduplication", "false") or "false").lower() == "true"
    if not content_dedup:
        findings.append(Finding(
            code="R9",
            severity="low",
            attribute="ContentBasedDeduplication",
            title="FIFO queue with content-based deduplication off requires producer-supplied dedup IDs",
            detail=(
                "ContentBasedDeduplication is off on a FIFO queue, so SQS will not derive "
                "a deduplication ID from the message body. Every producer must supply an "
                "explicit MessageDeduplicationId, or duplicate sends within the 5-minute "
                "dedup window are accepted as distinct messages. Whether the producers "
                "actually send that ID is a property of the producers, not of this queue "
                "(see boundary): flagged so the contract is verified rather than assumed."
            ),
            recommendation="Either enable ContentBasedDeduplication, or confirm every producer sets MessageDeduplicationId.",
        ))
    return findings


def _boundary_notes(attrs: dict[str, str], has_dlq: bool) -> list[str]:
    """The wall. Every audit names what the static config cannot answer."""
    notes = [
        "Consumer processing time is not a queue attribute. Whether VisibilityTimeout is "
        "actually long enough to avoid double-delivery (R5) needs the consumer's runtime "
        "behaviour, which lives outside SQS. Join: queue to its consumers.",
        "Live behaviour (redrive volume, ApproximateAgeOfOldestMessage, in-flight count, "
        "empty-receive rate) is CloudWatch time-series, not static attributes. This audit "
        "reads the configuration, not what the queue is doing right now. Join: queue to its "
        "metrics over time.",
        "The effective set of principals that can SendMessage / ReceiveMessage is the union "
        "of this resource Policy and every IAM identity policy in the account. Only the "
        "resource policy is visible here (R7). Join: queue to the account's IAM graph.",
        "Whether the producers writing to this queue are the intended ones, and whether "
        "anything is draining the DLQ at all, needs the producer and consumer inventory. "
        "Join: queue to the services on either side of it.",
    ]
    if has_dlq:
        notes.append(
            "A DLQ with messages in it is only useful if something inspects and redrives "
            "them. This audit confirms the DLQ is wired and sized correctly; it cannot "
            "confirm anyone is watching it. Join: DLQ to its operational owner."
        )
    return notes


def run_audit(
    fixture_dir: Path,
    is_processing_queue: bool = True,
) -> Audit:
    """End-to-end: load the queue (and its DLQ if present), run all checks, return the Audit.

    `is_processing_queue` tells the audit whether a missing DLQ is a finding (R1). A pure
    buffer/fan-out queue with an at-least-once contract elsewhere may legitimately have no
    DLQ; the caller asserts the queue's role rather than the audit guessing it.
    """
    attrs = load_attributes(fixture_dir / "queue.json")
    dlq_path = fixture_dir / "dlq.json"
    dlq_attrs = load_attributes(dlq_path) if dlq_path.exists() else None

    findings: list[Finding] = []
    redrive_findings, has_dlq = check_redrive_wiring(attrs, dlq_attrs, is_processing_queue)
    findings += redrive_findings
    findings += check_lifecycle_timing(attrs)
    findings += check_exposure(attrs)
    findings += check_fifo_invariants(attrs)

    findings.sort(key=lambda f: (_SEVERITY_RANK[f.severity], f.code))

    return Audit(
        queue_arn=attrs.get("QueueArn", ""),
        is_fifo=(attrs.get("FifoQueue", "false") or "false").lower() == "true",
        has_dlq=has_dlq,
        findings=findings,
        boundary=_boundary_notes(attrs, has_dlq),
    )
