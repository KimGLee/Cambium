# Role Registry

Interface: [Role Registry slot](../../../README.md#role-registry-slot)

## Process Roles

Use an actor or system ID/name for each binding.

| Kernel role | Bound actor or system ID/name |
|---|---|
| `proposer` | Workshop volunteer on shift |
| `gatekeeper` | Service lead on shift |
| `executor` | Workshop volunteer on shift |
| `stopper` | Workshop coordinator |

## Knowledge Host

| Kernel role | Binding |
|---|---|
| `knowledge-host` | Shared Markdown folder on the workshop machine |
| `knowledge-host UI` | The workshop machine's Markdown editor |

## Metric Traceability Roles

- Applicability: Not applicable — this corpus reports no evaluated metric; its numbers are published figures quoted from a named document revision or single measurements retained on a service case.

When configured, bind each role to a profile field or identifier.

| Kernel role | Profile field or identifier |
|---|---|

## Extension Roles

- Registration: Configured

| Role ID | Bound actor or system ID/name | Responsibility |
|---|---|---|
| `service-lead` | The service lead named on the shift rota | Accept or reject semantic capability acceptance for the corpus plan, and sign the workshop's finish condition on a member's service. |

`service-lead` is the role the Corpus Planning slot binds as its `pass_authority.role_id`. It is registered here as a profile extension role rather than reusing a kernel process role, because deciding that a capability is semantically covered is not the same act as stopping work.
