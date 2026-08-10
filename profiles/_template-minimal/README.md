# Minimal-depth Template

## What This Is

This directory is the pre-closed, minimal depth of the same 13-slot profile
interface that `profiles/_template/` presents in full. Both depths produce
fully conformant profiles; the difference is how many answers ship pre-closed
or pre-filled here instead of asked. It is a template, not a profile: the
identity is unfilled, so nothing in this directory is selectable or runnable
in place. The normative interface remains [profiles/README.md](../README.md).

Use this depth when the corpus is bounded and maintained one note at a time.
Use `profiles/_template/` when you intend to answer every switch explicitly.
Every closed switch here can be opened later through ordinary Standards
adoption without interrupting an active task; a corpus that grows into
multi-batch construction must configure Corpus Planning at that point
(K02/03 owns that judgment, not this template).

## What Ships Pre-closed

Every slot switch with a legal exit state is already in it, with a
scenario-generic reason: Corpus Planning and Structure Registry
(`not-applicable`), Metadata Contract (`kernel-defaults`), Priority Rubric
(`No grants`), Expression Layer (`None`, Artifact block deleted), the four
Routing And Gate registrations (`None`), the optional Language and Source
registrations (`None`), Metric Traceability (`Not applicable`), Extension
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
[interview.yaml](interview.yaml) carries them as a machine-readable interview
an assisting agent can conduct — including a setup step (S0: corpus location,
created if absent) before the first question and a closing review (C3: closed
switches, derived fills, and remaining needs) after the last;
[answer-patterns.md](answer-patterns.md) carries the shapes to propose. In
table form:

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
| 12 | The two judgment items' IDs, objects, and owner paths | `registries/audit-dimensions.md` | Fixed cells pre-filled; see the self-path checklist |

## Self-path Checklist (Rewrite Before Use)

`check_profile.py` will not notice a path that points at someone else's
profile; the batch-close scan would then run the wrong configuration. After
copying this template to `profiles/<profile-id>/`, every one of these cells
must name **your** profile's path:

1. `registries/registered-scans.md` — the verifier command's `--config` path.
2. `registries/audit-dimensions.md` — both predicate-owner cells (the
   foundation item points at your `scope-and-architecture.md#Foundation Depth
   Requirements`; the residual item points at your
   `registries/audit-dimensions.md#Residual Disposition`).

## Validation

```text
cp -R profiles/_template-minimal profiles/<profile-id>
rm profiles/<profile-id>/{README.md,interview.yaml,answer-patterns.md}
# orientation files, consumed during filling; never profile policy
# answer the twelve decisions above, then:
python3 Tools/check_profile.py profiles/<profile-id>
```

The template itself is not validated in place, exactly as with
`profiles/_template/`. Selection still requires R09 adoption; copying,
filling, and checking do not activate anything.
