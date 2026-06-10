"""
Replay test for examples/02-dns-resolution-failure.md.

Runs the reference methodology against the DNS fixtures and asserts the
methodology produces the expected classification, mitigation, and handoff.

Stdlib only. Run with: `python tests/replay_02_dns.py`.
Exits 0 on success, 1 on any assertion failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _methodology import run_investigation  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "02-dns-resolution-failure"


def main() -> int:
    inv = run_investigation(
        fixture_dir=FIXTURE_DIR,
        t0_iso="2026-04-08T09:47:00Z",
        tnow_iso="2026-04-08T09:53:00Z",
        failing_surface_hints=["coredns", ".internal"],
    )

    assertions = [
        # Step 1: window anchored correctly.
        (inv.window[0].isoformat() == "2026-04-08T09:32:00+00:00", f"window start expected 09:32:00Z, got {inv.window[0].isoformat()}"),

        # Step 2: change surface contains the CoreDNS ConfigMap change and no code deploys.
        (len(inv.change_surface) == 1, f"expected 1 change in window, got {len(inv.change_surface)}"),
        (inv.change_surface[0]["kind"] == "infra", f"expected infra change, got {inv.change_surface[0]['kind']}"),
        (inv.change_surface[0].get("resource") == "kube-system/coredns", f"expected coredns ConfigMap, got {inv.change_surface[0].get('resource')}"),

        # Step 3: classified as DNS (not OOM, not deploy-correlator).
        (inv.classified_path == "DNS", f"expected DNS, got {inv.classified_path}"),
        (any("DNS error log lines" in e for e in inv.classification_evidence), f"expected DNS log evidence, got {inv.classification_evidence}"),

        # Step 4: at least three independent signal sources.
        (len({s["source"] for s in inv.confirming_signals}) >= 3, f"expected >=3 independent signal sources, got {len({s['source'] for s in inv.confirming_signals})}"),

        # Step 5: blast radius reflects elevated but partial error rate (intermittent DNS).
        (1 <= inv.blast_radius["error_rate_peak_pct"] <= 10, f"expected partial error rate (1-10%), got {inv.blast_radius['error_rate_peak_pct']}"),

        # Step 6: mitigation ranked, revert first (ConfigMap revert is the path).
        (inv.mitigation_ranked[0]["action"] == "revert", f"expected revert as first mitigation, got {inv.mitigation_ranked[0]['action']}"),

        # Step 7: handoff includes DNS classification, no escalation needed.
        (inv.handoff["classified_path"] == "DNS", "handoff payload should carry DNS classification"),
        (inv.escalate_to_human is False, f"DNS-with-3-signals should not escalate, got escalation_reasons={inv.escalation_reasons}"),
    ]

    failed = [msg for ok, msg in assertions if not ok]
    if failed:
        print("FAIL: replay_02_dns")
        for msg in failed:
            print(f"  - {msg}")
        return 1

    print(f"PASS: replay_02_dns ({len(assertions)} assertions)")
    print(f"  classified_path: {inv.classified_path}")
    print(f"  recommended:     {inv.mitigation_ranked[0]['action']} -> {inv.mitigation_ranked[0]['target']}")
    print(f"  signals:         {len(inv.confirming_signals)} from {len({s['source'] for s in inv.confirming_signals})} sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
