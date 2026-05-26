"""
Replay test for examples/04-deploy-correlator-serialization.md.

Stdlib only. Run with: `python tests/replay_04_deploy_correlator.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _methodology import run_investigation  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "04-deploy-correlator-serialization"


def main() -> int:
    inv = run_investigation(
        fixture_dir=FIXTURE_DIR,
        t0_iso="2026-02-15T13:25:00Z",
        tnow_iso="2026-02-15T13:30:00Z",
        failing_surface_hints=["cart", "serializer"],
    )

    assertions = [
        (inv.window[0].isoformat() == "2026-02-15T13:10:00+00:00", f"window start expected 13:10:00Z, got {inv.window[0].isoformat()}"),

        # Step 2: one change in window, the v6.4.0 deploy.
        (len(inv.change_surface) == 1, f"expected 1 change in window, got {len(inv.change_surface)}"),
        (inv.change_surface[0]["version"] == "v6.4.0", f"expected v6.4.0, got {inv.change_surface[0].get('version')}"),

        # Step 3: classified as deploy-correlator (NOT OOM, NOT cascade, NOT DNS).
        (inv.classified_path == "deploy-correlator", f"expected deploy-correlator, got {inv.classified_path}"),
        (any("cart" in e.lower() or "serializer" in e.lower() for e in inv.classification_evidence), f"expected cart/serializer surface match, got {inv.classification_evidence}"),

        # Step 4: at least 3 independent signal sources.
        (len({s["source"] for s in inv.confirming_signals}) >= 3, f"expected >=3 signal sources, got {len({s['source'] for s in inv.confirming_signals})}"),

        # Step 5: blast radius is partial, low single-digit error rate.
        (2 <= inv.blast_radius["error_rate_peak_pct"] <= 10, f"expected partial error rate (2-10%), got {inv.blast_radius['error_rate_peak_pct']}"),

        # Step 6: mitigation leads with revert.
        (inv.mitigation_ranked[0]["action"] == "revert", f"expected revert as first mitigation, got {inv.mitigation_ranked[0]['action']}"),
        (inv.mitigation_ranked[0].get("target", "").startswith("checkout-api"), f"expected revert target to be checkout-api, got {inv.mitigation_ranked[0].get('target')}"),
        # Should NOT propose circuit_breaker (that's cascade-specific).
        (not any(m["action"] == "circuit_breaker" for m in inv.mitigation_ranked), "should NOT recommend circuit_breaker for deploy-correlator"),

        # Step 7: handoff payload + no escalation.
        (inv.handoff["classified_path"] == "deploy-correlator", "handoff payload should carry deploy-correlator"),
        (inv.escalate_to_human is False, f"deploy-correlator with surface match should not escalate, got {inv.escalation_reasons}"),
    ]

    failed = [msg for ok, msg in assertions if not ok]
    if failed:
        print("FAIL: replay_04_deploy_correlator")
        for msg in failed:
            print(f"  - {msg}")
        return 1

    print(f"PASS: replay_04_deploy_correlator ({len(assertions)} assertions)")
    print(f"  classified_path: {inv.classified_path}")
    print(f"  recommended:     {inv.mitigation_ranked[0]['action']} -> {inv.mitigation_ranked[0]['target']}")
    print(f"  signals:         {len(inv.confirming_signals)} from {len({s['source'] for s in inv.confirming_signals})} sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
