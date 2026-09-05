# Worked Planning Example Profile

This non-normative example describes a community bicycle workshop's wheel-service corpus. It demonstrates a configured Corpus Planning slot with three filled planning artifacts over six real Markdown pages. It is not a template, an adoption certificate, or a claim that a corpus of this size requires planning.

[profile.toml](profile.toml) is the only Profile answer entrypoint. Its `corpus-planning` slot binds the three planning artifacts, capability scale and semantic pass authority; its `profile-scope` slot binds the real layer directories. The retained integer `execution_default_overrides.concurrency_cap = 1` is the example's existing override, separate from its numeric priority quotas.

## Package Contents

- [Global Map](planning/global_map.yaml): real page owners and typed dependencies.
- [Capability Matrix](planning/capability_matrix.yaml): capability positions, evidence, target levels, and Gap links.
- [Gap Register](planning/gap_register.yaml): candidate, confirmed, deferred, and rejected examples.
- [Six-page corpus](corpus/): the pages referenced by those artifacts.
- [Judgment policies](policies/residual-disposition.md): preserved residual disposition, capability-evidence reuse, and source-revision candidate rules.
- [Residual scan parameters](scan-configs/residual-scan.yaml): the declared scan's literal parameters.

The corpus is nested here to make the public example's references self-contained. A real adopter's corpus lives outside its Profile package. Moving the answer shape to another repository requires explicit new Profile and corpus bindings; neither checker guesses replacement paths.

The example exercises typed dependency edges, explicit empty lists where their owner permits them, bidirectional Matrix–Gap links, and the `emits`, `consumes`, and `triggers` evidence roles. Its capability-evidence judgment reuses the existing corpus-plan structural receipt rather than inventing another verdict.

Promoted and resolved Gaps are absent because they require actual Coverage and runtime state. There is no semantic acceptance receipt, expression layer, readiness axis, supplemental route, or extension Gate. The structural check cannot supply semantic acceptance or select the example.

## Validation Provenance

| Validator | Tool version | Command | Expected result |
|---|---|---|---|
| `check_profile` | `2.2.0` | `python3 Tools/check_profile.py profiles/examples/worked-planning` | exit 0 |
| `check_corpus_plan` | `1.7.0` | `python3 Tools/check_corpus_plan.py . --profile profiles/examples/worked-planning/profile.toml` | exit 0 |
| `check_residual_content` | `1.2.0` | `python3 Tools/check_residual_content.py . --scan-id worked-planning-case-residuals --config profiles/examples/worked-planning/scan-configs/residual-scan.yaml --time-limit 55` | exit 0 |

The positive residual witness exists in `corpus/Service Cases`. A passing scan proves its bounded registered predicate, not case quality or adoption. These commands must be re-run when their owner contracts or tools change.

New Profiles start as empty candidates created by the Agent. The interview gathers the user's own scope, capability scale, source policy, priority choices, roles, and authorization; this workshop's values remain an example.
