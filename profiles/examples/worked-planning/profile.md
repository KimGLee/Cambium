# Worked Planning Example Profile

Normative interface: [Profile interface](../../README.md). Example namespace rules: [Examples](../README.md).

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

## Execution Default Overrides

Allowed items: [execution-default registry](../../../kernel/K00%20Standards%20Control/execution-defaults-base.yaml).

The one registered row is deliberate: `priority_quota.P0` is the item this
distribution's tools actually resolve from the manifest, so the row changes
observable behaviour rather than recording an intention. The value is the P0
share target as a percentage; `10` is stricter than the kernel default this
profile's owner module publishes.

| Override item ID from the registry | Non-default profile value |
|---|---|
| `priority_quota.P0` | 10 |
