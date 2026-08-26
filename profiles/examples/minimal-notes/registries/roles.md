# Role Registry

Interface: [Kernel-owned Profile interface](../../../../kernel/K00%20Standards%20Control/19%20Profile%20Extension%20Interface.md) — Role Registry slot

## Process Roles

Use an actor or system ID/name for each binding.

| Kernel role | Bound actor or system ID/name |
|---|---|
| `proposer` | Assisting agent session |
| `gatekeeper` | Vault maintainer |
| `executor` | Assisting agent session |
| `stopper` | Vault maintainer |

## Knowledge Host

| Kernel role | Binding |
|---|---|
| `knowledge-host` | A plain Markdown directory tree on the maintainer's machine |
| `knowledge-host UI` | None — headless |

## Metric Traceability Roles

- Applicability: Not applicable — this vault reports no evaluated metric; every number in it is a setting read off a device, recorded with its retrieval date under Source Policy.

When configured, bind each role to a profile field or identifier.

| Kernel role | Profile field or identifier |
|---|---|

## Extension Roles

- Registration: None

| Role ID | Bound actor or system ID/name | Responsibility |
|---|---|---|
