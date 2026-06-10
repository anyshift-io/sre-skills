"""
Per-fixture queue contexts and expected answers, used by run_eval.py.

The "expected_*" fields are the deterministic answers from _audit.py run against
each fixture (see tests/replay_*.py). They are the source of truth the judge model
compares the agent's output against, so they are computed here by importing the
reference implementation rather than hand-copied (which would drift).

Stdlib only. No external dependencies.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = TESTS_DIR.parent / "fixtures"

sys.path.insert(0, str(TESTS_DIR))
from _audit import run_audit  # noqa: E402

# Each entry pairs a fixture with the human-readable context the eval feeds the agent,
# plus the rule(s) the deterministic audit produces (the judge's ground truth). Keep this
# list aligned with the replay_*.py files under tests/.
QUEUES = [
    {
        "id": "01-no-dlq",
        "queue": "payments-capture",
        "role": "A worker fleet receives capture events and calls a payment processor.",
        "is_processing_queue": True,
        "expected_headline": "No dead-letter queue on a processing queue; poison messages are retried until retention expiry, then silently deleted.",
        "expected_top_fix": "Attach a RedrivePolicy to a DLQ with maxReceiveCount in the 3-10 band.",
        "expected_boundary_join": "queue to its metrics over time (is a poison message in the queue right now) and queue to its consumers (is this really a processing queue).",
    },
    {
        "id": "02-dlq-retention-shorter-than-source",
        "queue": "order-events",
        "role": "Order events processed by a worker fleet, with a dead-letter queue attached.",
        "is_processing_queue": True,
        "expected_headline": "DLQ retention (1 day) is not longer than the source (4 days); because SentTimestamp does not reset on redrive, late failures arrive in the DLQ already past its limit and are deleted on arrival.",
        "expected_top_fix": "Raise the DLQ MessageRetentionPeriod above the source's, ideally to the 14-day maximum.",
        "expected_boundary_join": "DLQ to its metrics over time (how many were dropped) and DLQ to its operational owner.",
    },
    {
        "id": "03-maxreceivecount-too-low",
        "queue": "email-dispatch",
        "role": "Sends transactional email via an upstream provider, with a dead-letter queue attached.",
        "is_processing_queue": True,
        "expected_headline": "maxReceiveCount=1 dead-letters good messages on the first transient failure; the DLQ fills with recoverable messages that mask genuine poison.",
        "expected_top_fix": "Raise maxReceiveCount into the 3-10 band so transient failures are retried before quarantine.",
        "expected_boundary_join": "DLQ to its consumers (ratio of transient to poison) and queue to its metrics over time.",
    },
    {
        "id": "04-poison-ages-out-before-dlq",
        "queue": "ledger-reconcile",
        "role": "A daily reconciliation worker, with a dead-letter queue attached and generous retention.",
        "is_processing_queue": True,
        "expected_headline": "maxReceiveCount (1000) x VisibilityTimeout (900s) = 900000s exceeds MessageRetentionPeriod (345600s), so poison messages age out and are deleted before they ever reach the correctly-wired DLQ.",
        "expected_top_fix": "Lower maxReceiveCount or VisibilityTimeout (or raise retention) so maxReceiveCount x VisibilityTimeout stays well under retention.",
        "expected_boundary_join": "queue to its metrics over time and queue to its consumers (real receive cadence).",
    },
    {
        "id": "05-default-visibility-short-retention",
        "queue": "click-events",
        "role": "A high-volume analytics ingest queue, with a dead-letter queue attached.",
        "is_processing_queue": True,
        "expected_headline": "Two soft flags: VisibilityTimeout at the 30s default (possible double-delivery) and MessageRetentionPeriod at 300s (a short outage loses messages). Neither is a confirmed bug from config alone.",
        "expected_top_fix": "Raise retention to cover a plausible outage; set VisibilityTimeout deliberately above consumer p99 processing time.",
        "expected_boundary_join": "queue to its consumers (processing-time distribution) and queue to its metrics over time.",
    },
    {
        "id": "06-public-queue-policy",
        "queue": "inbound-webhooks",
        "role": "Intended to receive events from one specific SNS topic, with a dead-letter queue attached.",
        "is_processing_queue": True,
        "expected_headline": "Resource policy allows Principal:* for SendMessage with no narrowing Condition (a public queue), and server-side encryption at rest is off.",
        "expected_top_fix": "Add a Condition pinning the principal to the intended aws:SourceArn (or name explicit principal ARNs); enable SSE.",
        "expected_boundary_join": "queue to the account's IAM graph (resource policy is only half the effective access).",
    },
    {
        "id": "07-fifo-dedup-off",
        "queue": "inventory-updates.fifo",
        "role": "A FIFO queue chosen for ordering and exactly-once processing of stock adjustments, with a dead-letter queue attached.",
        "is_processing_queue": True,
        "expected_headline": "FIFO queue with ContentBasedDeduplication off: exactly-once now depends entirely on every producer supplying a MessageDeduplicationId, which the queue cannot enforce.",
        "expected_top_fix": "Enable ContentBasedDeduplication, or confirm every producer sets MessageDeduplicationId.",
        "expected_boundary_join": "queue to its producers (do they send the dedup ID).",
    },
    {
        "id": "08-clean-standard",
        "queue": "notification-fanout",
        "role": "Subscribed to an SNS topic, processed by a worker fleet, with a dead-letter queue attached.",
        "is_processing_queue": True,
        "expected_headline": "No findings. The queue is correctly configured, including a wildcard-principal policy that is correctly narrowed by aws:SourceArn (the legitimate SNS-to-SQS pattern).",
        "expected_top_fix": "None. Do not invent a finding. Still report the boundary.",
        "expected_boundary_join": "queue to its metrics over time, queue to the account's IAM graph, DLQ to its owner (a clean config is not a clean system).",
    },
]


def fixture_dir(queue: dict) -> Path:
    return FIXTURES_DIR / queue["id"]


def load_fixture_text(queue: dict) -> str:
    """The raw GetQueueAttributes JSON the agent is given: the source queue and its DLQ."""
    d = fixture_dir(queue)
    parts = []
    q = json.loads((d / "queue.json").read_text())
    parts.append("SOURCE QUEUE (aws sqs get-queue-attributes --attribute-names All):\n" + json.dumps(q, indent=2))
    dlq_path = d / "dlq.json"
    if dlq_path.exists():
        dlq = json.loads(dlq_path.read_text())
        parts.append("DEAD-LETTER QUEUE (aws sqs get-queue-attributes --attribute-names All):\n" + json.dumps(dlq, indent=2))
    return "\n\n".join(parts)


def expected_audit(queue: dict) -> dict:
    """Run the deterministic reference audit to get the ground-truth findings for the judge."""
    audit = run_audit(fixture_dir(queue), is_processing_queue=queue["is_processing_queue"])
    return {
        "codes": sorted(audit.codes()),
        "top_severity": audit.top_severity,
        "clean": audit.clean,
        "boundary_count": len(audit.boundary),
    }


if __name__ == "__main__":
    # `python tests/eval/queues.py` prints the ground-truth answers, no API needed.
    for q in QUEUES:
        exp = expected_audit(q)
        print(f"{q['id']:<40} codes={exp['codes']!s:<18} top={exp['top_severity']} clean={exp['clean']}")
