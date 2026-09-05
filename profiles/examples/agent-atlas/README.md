# Agent Systems Atlas Example Profile

This package is a non-normative example for a Chinese-first engineering knowledge corpus. It is not a template, live Atlas mirror, selected Profile, or adoption certificate. Cambium owns the public example; the live adopter remains responsible for its own policies and adoption.

[profile.toml](profile.toml) is the single answer entrypoint. Its stable slots contain scope, planning and structure bindings, priority policies, language and metadata choices, source policy, roles, and extension registrations. The empty `execution_default_overrides` mapping preserves the example's existing absence of explicit overrides.

The package also contains:

- [Expression contracts](policies/expression-contracts.md), the sole bodies for Interview Topic Guide, Roadmap, and Cheat Sheet policies.
- [Judgment policy](policies/residual-disposition.md), the sole residual-disposition body.
- [Residual scan parameters](scan-configs/residual-scan.yaml), consumed by the declared scan capability.

K11 retains the common expression floor. The example's Topic Guide policy requires Chinese and English versions of its 30-second and 90-second answers; follow-up answers need not be bilingual. It registers no independent Interview-readiness axis. Interview work uses the existing Kernel R05 route with no supplemental Profile Read Set.

The Profile owns the scan's instance identity, scope, candidate boundary, judgment binding, and parameters. The executable remains the generic Tool capability. A residual candidate is not a defect count, deletion list, automatic Gate failure, or migration authorization.

## Provenance

The original package was seeded from the Agent Systems Atlas Profile at commit `15df10eac89cafd381b145c48659c4a525f93f6d`. Its public values were reconciled on 2026-09-04, then migrated to the structured Profile interface with package-local references. These are content-provenance statements; they do not assert current adoption by the live repository.

The migration preserves the previously supplied rendering registration alongside the other slot values. Independent policy bodies retain their original prose and headings. Old table files are no longer parallel policy owners.

## Validation Provenance

| Validator | Tool version | Command | Expected result |
|---|---|---|---|
| `check_profile` | `2.2.0` | `python3 Tools/check_profile.py profiles/examples/agent-atlas` | exit 0 |

The example intentionally omits the private corpus and the three externally bound planning artifacts. A structural Profile check cannot prove those artifacts exist or that the corpus plan was accepted. Run corpus-plan validation only after a real adopter materializes its own bindings. The separate [Worked Planning example](../worked-planning/README.md) carries actual planning artifacts.

The user supplies their own identity, paths, language, sources, roles, scope, priorities, and authorization choices. The Agent may use this example to explain answer specificity, then writes only the confirmed repository-specific answers.
