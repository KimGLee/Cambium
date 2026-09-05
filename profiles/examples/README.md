# Profile Examples

These packages are non-normative, filled examples of structured Profile answers. They show domain choices; they do not define the public interface, supply defaults, confirm another repository's policies, or select a Profile.

[The Kernel interface](../../kernel/K00%20Standards%20Control/profile-interface.yaml) registers the stable slots and their separate semantic owners. Each example has one `profile.toml` entrypoint with embedded slot values. Necessary independent policy bodies and registered scan parameters remain explicitly referenced support files; they do not create additional slots.

Examples under `profiles/examples/` are intentionally not selectable in place. For a new Profile, the conducting Agent creates a direct-child candidate under `profiles/<profile-id>/` and records answers through the interview. The user does not copy or edit the example's files. Checking answers and selecting a version remain separate operations.

- [Agent Systems Atlas](agent-atlas/README.md) shows Chinese-first engineering knowledge, explicit structure and metadata choices, Interview expression contracts, and one generic residual scan. It carries no private corpus, selected state, or adoption evidence.
- [Worked Planning](worked-planning/README.md) contains a configured Corpus Planning slot, three planning artifacts, and a six-page workshop corpus so its references can be checked locally.

The examples do not exhaust the interface. Neither is a worked example of a supplemental Profile Read Set, a promoted/resolved Gap with real runtime state, or a separate readiness Gate. Missing examples do not forbid legal extensions defined by their owner.

Each package records its validation commands and tool versions. Re-run them when the interface or tools change; validation provenance does not confer adoption or semantic acceptance.
