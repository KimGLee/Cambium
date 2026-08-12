# Expression Layer

Interface: [Expression Layer Entry slot](../README.md#expression-layer-entry-slot)

## Registered Artifacts

- Registration: None

This profile registers no expression artifact, so it supplies no concrete R05
target: the corpus's readers use the canonical pages directly, and no derived,
reader-facing artifact exists to keep in sync. Registering `None` does not
remove R05 — an R05 task on this profile has no valid target and stops instead
of inventing one. The `Expression Layer Predicate` in
[Profile Scope](scope-and-architecture.md#placement-layer-registrations) is
`always false` for the same reason, and
[vocabulary-extensions.yaml](vocabulary-extensions.yaml) registers no
readiness axis.

The `### Artifact` block shipped by `profiles/_template/expression-layer.md`
is deleted rather than left empty, as that template instructs. Open this slot
later, through ordinary Standards adoption, when a derived reader-facing
artifact (a card set, a digest, a published view) first appears.
