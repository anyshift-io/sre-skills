# sre-skills

[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](./LICENSE)

Open-source library of methodology-shaped SRE skills for AI agents.

Built and maintained by [Anyshift](https://www.anyshift.io). Each skill packages a SRE methodology (investigating an incident, handing over oncall, authoring a postmortem) as a self-contained module an AI agent can run.

## How this works

Three layers, in order of integration depth:

1. **Vendor-neutral default.** Every skill runs end-to-end without an Anyshift dependency. You get the methodology, the worked examples, and the fixture-based replay tests. This is the layer the open-source community contributes to.

2. **Anyshift MCP as optional context primer.** Skills can opt-in to richer context from the Anyshift MCP server. Each skill README publishes a measured "with vs without" delta so the value is explicit, not assumed.

3. **Annie pre-loaded.** Users running Anyshift's Annie agent get the skills already loaded, with infrastructure context (Terraform state, AWS / GCP / Azure inventory, recent deploys) wired in.

## Skills

| Skill | Status | What it does |
|---|---|---|
| `incident-investigator` | *Shipping by end of May 2026* | Investigates a live incident: correlates deploys, traces, logs, recent IAM changes. Covers OOM, DNS, cascading-failure, deploy-correlator paths. |
| `change-impact-analyzer` | *Shipping by end of May 2026* | Pre-flight checks: IAM blast radius, drift detection, what this PR breaks. |
| `oncall-handover` | *Shipping by end of May 2026* | Reviews cert expiry, deploy state, SLO burn during oncall handover. |
| `postmortem-author` | *Shipping by end of May 2026* | Timeline reconstruction, contributing factors, impact quantification. |
| `reliability-auditor` | *Shipping by end of May 2026* | Production-readiness audit. |

## Quality bar

Every skill in this repo ships with:

- Two worked examples (real incidents or canonical scenarios).
- Fixture-based replay tests that work without external credentials.
- A 60 to 120 second screen recording showing the skill in action.
- An explicit failure-modes section: where the skill is wrong, where the agent should escalate to a human.

This bar exists because methodology skills age fast if they're not exercised against real fixtures.

## Adjacent: awesome-sre-skills

For a curated index of SRE skills (ours and others), MCP servers, and reading, see [anyshift-io/awesome-sre-skills](https://github.com/anyshift-io/awesome-sre-skills).

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

[Apache 2.0](./LICENSE).
