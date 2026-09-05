package profile

// GENERATED: do not edit this projection.
// Semantic owner: K08/01+K08/03+K08/05
// Source: kernel/K08 Metadata and Status/vocabulary-extensions-contract.yaml
// Source SHA256: 2f142b79eb1fdb6122ef49e67b1832309e6341a0c94a7a97e0fd431d219645b0
// Projected checks: object fields, scalar/list types, declared enums and applicability shapes.
// Owner evaluator still checks identities, graph/reference closure, tightening,
// conditional nonempty configuration, external vocabularies and evidence.
#VocabularyExtensions: {
    schema_version: 1
    frontmatter_extensions: {fields: [...#Text]}
    fields: {[=~"^[a-z][a-z0-9_]*$"]: {values: [...#Text], owner?: #Text, role?: #Text}}
    volatility_defaults: {[string]: #Text}
}
