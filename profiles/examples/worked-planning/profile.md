# Profile Manifest

Common interface: [Kernel Profile registry](../../../kernel/K00%20Standards%20Control/profile-interface.yaml).

## Profile Identity

- `profile_id`: `worked-planning`

## Implemented Slots

- `Profile Scope`: `scope-and-architecture.md`
- `Corpus Planning`: `corpus-planning.yaml`
- `Structure Registry`: `structure-registry.yaml`
- `Metadata Contract`: `metadata-contract.yaml`
- `Priority Rubric`: `priority-rubric.md`
- `Vocabulary Extensions`: `vocabulary-extensions.yaml`
- `Language Contract`: `language-contract.md`
- `Expression Layer Entry`: `expression-layer.md`
- `Source Policy`: `source-policy.md`
- `Role Registry`: `registries/roles.md`
- `Audit Dimension Registry`: `registries/audit-dimensions.md`
- `Registered Scan Registry`: `registries/registered-scans.md`
- `Routing And Gate Registry`: `registries/routing-and-gates.md`
- `Escalation Policy`: `escalation-policy.md`

## Execution Default Overrides

Allowed items: [execution-default registry](../../../kernel/K00%20Standards%20Control/execution-defaults-base.yaml).

The one registered row is deliberate: `concurrency_cap` is an item this distribution's tools actually resolve from the manifest, so the row changes observable behaviour rather than recording an intention. Quota targets are not overrides -- they live in this profile's `Priority Rubric` under `Priority Quota`, beside the grant predicates and their rationale.

| Override item ID from the registry | Non-default profile value |
|---|---|
| `concurrency_cap` | 1 |
