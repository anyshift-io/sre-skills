# Contributing to sre-skills

This is the methodology-shaped SRE skills library maintained by Anyshift. Contributions are welcome from anyone, individuals and other vendors included.

## The bar

Every skill in this repo ships with:

1. **Two worked examples.** Real incidents, canonical scenarios, or both. Show the methodology in motion, not just described.
2. **Fixture-based replay tests.** The skill must be runnable end-to-end against committed fixtures, with no external credentials. If your skill calls an API, the fixtures stand in for the API in tests.
3. **A 60 to 120 second screen recording.** Show the skill working. Hosted in the skill directory or linked from the README.
4. **An explicit failure-modes section.** Where is this skill wrong? Where should an agent escalate to a human? List the failure modes honestly.

Skills that don't meet this bar stay in PR until they do.

## Vendor-neutral default

The default code path for every skill must run end-to-end without depending on Anyshift, Anyshift MCP, or Annie. Anyshift integration is a documented opt-in path with a measured "with vs without" delta in the skill README.

This is non-negotiable. A skill that only works with Anyshift loaded belongs in a different repo.

## Skill layout

The canonical layout is established by `skills/incident-investigator/` (the reference template). Mirror that structure for new skills.

The reference template is shipping by end of May 2026. Until then, open a discussion if you want to start a new skill and we'll coordinate on layout.

## How to add a new skill

1. Fork the repo.
2. Create `skills/<skill-name>/` mirroring the reference template.
3. Open a PR. Reviewers check: vendor-neutral runnability, the four quality-bar items above, and methodology soundness.

## What goes outside this repo

- General awesome-list entries: see [anyshift-io/awesome-sre-skills](https://github.com/anyshift-io/awesome-sre-skills).
- Skills that are vendor-specific by design (e.g. only run with a particular observability stack): keep them in your own repo, link from awesome-sre-skills.

## License

By contributing, you agree your contribution is licensed under [Apache 2.0](./LICENSE).
