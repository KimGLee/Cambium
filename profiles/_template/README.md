# Profile Template

## What This Is

This directory is the 14-slot profile interface as a copyable form. It is a
template, not a profile: the identity is unfilled, so nothing here is
selectable or runnable in place. The normative interface remains
[profiles/README.md](../README.md).

Every slot switch that has a legal exit state ships in it, and every
operational answer that generalizes ships pre-filled. What is left open is
exactly the set of decisions no template can make. A closed switch is not a
lesser profile: a filled copy is fully conformant either way, and each switch
opens later through ordinary Standards adoption without interrupting an active
task.

The shapes for every closed branch travel with the slot file that closes it,
as comments. Opening a switch therefore needs no second document — read the
comment block in that file, uncomment or write the rows, and re-run
`check_profile.py`.

## What Ships Pre-closed

Every slot switch with a legal exit state is already in it, with a
scenario-generic reason: Corpus Planning and Structure Registry
(`not-applicable`), Metadata Contract (`kernel-defaults`), Priority Rubric
(`No grants`), Expression Layer (`None`, Artifact block deleted), the four
Routing And Gate registrations (`None`), the Escalation Policy registry
(`None`), the optional Language and Source registrations (`None`), Metric Traceability (`Not applicable`), Extension
Roles and Extension Dimensions (`None`), Production System Reasoning,
Representative Sample Plan, and Dependency-ordered Build Sequence
(`Not applicable`), and an empty Execution Default Overrides table. Confirm
each reason still holds for your corpus; a pre-closed switch whose reason is
false for you is an unconfirmed answer, not a default.

## What Ships Pre-filled (Confirm, Don't Skip)

Operational answers carry generalized defaults you confirm or replace: the
process and host role bindings, the language display/naming/length rows, the
`general: slow` volatility domain, and the fixed cells of the two required
judgment items. These are template text, not kernel defaults; what you keep
becomes your profile's own answer.

## What Remains To Answer

The open placeholder markers are exactly the decisions no template can make.
The [adoption interview contract](../interview.yaml) carries them as a
machine-readable interview an assisting agent can conduct — including a setup
step (S0: corpus location, created if absent) before the first question and a
closing review (C3: closed switches, derived fills, and remaining needs)
after the last; the [answer patterns](../answer-patterns.md) carry the shapes
to propose. To answer every switch now rather than leaving the legal exit
states closed, the same contract walks its `expansion_packs` in the same
sitting; each pack names the slot it fills. In table form:

| # | Decision | File | Notes |
|---|---|---|---|
| 1 | `profile_id` | `profile.md` | Migration-grade: equals the directory name |
| 2 | Goal and readers | `scope-and-architecture.md` | |
| 3 | Body language | `language-contract.md` | Migration-grade; confirm the length unit with it |
| 4 | Excluded scope | `scope-and-architecture.md` | Pre-filled `None — no exclusions`; confirm or replace |
| 5 | Layers and directories | `scope-and-architecture.md` | Migration-grade; a flat corpus registers one layer, and the placement fallbacks reuse its ID |
| 6 | Priority factor(s) | `scope-and-architecture.md` | |
| 7 | Knowledge Spine | `scope-and-architecture.md` | One line is legal; pattern in the section note |
| 8 | Terminology class | `scope-and-architecture.md` | |
| 9 | Foundation-depth class and predicate | `scope-and-architecture.md` | Four-element pattern in the section note |
| 10 | Source authority, verification, staleness | `source-policy.md` | Own observation with a retrieval date is a registrable source |
| 11 | Residual scan | `registries/registered-scans.md` + `scan-configs/residual-scan.yaml` | Derive matchers from real corpus content; archetype in the registry note |
| 12 | The two judgment items' IDs, objects, and owner paths | `registries/audit-dimensions.md` | Fixed cells pre-filled; see the materialization checklist |

## Materialization Checklist (Rewrite Before Validation)

After copying this template to `profiles/<profile-id>/`, derive every one of
these cells from the new profile ID so each names **your** Profile's path.
`check_profile.py` resolves them as part of the `profile-load` Gate and fails
closed on a template, foreign-Profile, root-fallback, missing, aliased, or
ambiguous target; batch close consumes that same resolved contract before it
launches the scan.

1. `registries/registered-scans.md` — the verifier command's `--config` path.
2. `registries/audit-dimensions.md` — both predicate-owner cells (the
   foundation item points at your `scope-and-architecture.md#Foundation Depth
   Requirements`; the residual item points at your
   `registries/audit-dimensions.md#Residual Disposition`).

This remains a materialization step rather than an optional cleanup: the Gate
detects a stale path but never guesses or rewrites the intended profile ID.

## Validation

```text
python3 Tools/scaffold_profile.py . --profile-id <profile-id>           # dry-run
python3 Tools/scaffold_profile.py . --profile-id <profile-id> --apply
# answer the twelve decisions above, then:
python3 Tools/check_profile.py profiles/<profile-id>
```

The scaffolder copies exactly the whitelist in
[template-files.yaml](../template-files.yaml) (never this README) and derives
the materialization cells below. The manual no-agent fallback — copy the whitelisted
files by hand, delete nothing else, keep this README out — performs the same
checklist itself.

The template itself is never validated in place: its identity is unfilled, so
it is neither runnable nor selectable. Selection still requires R09 adoption;
copying, filling, and checking do not activate anything.
