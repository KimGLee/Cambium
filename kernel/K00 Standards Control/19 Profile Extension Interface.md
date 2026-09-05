# Profile Extension Interface

## Purpose

The Profile interface is the common boundary through which one adopting knowledge repository binds choices that the Kernel deliberately leaves open. The Kernel owns the existence, meaning, minimum constraints, and invalid forms of each extension point. A selected Profile owns only the confirmed instance value bound to it.

[`profile-interface.yaml`](profile-interface.yaml) identifies the common slot set, each semantic owner, and the complete set of stable contracts to evaluate. K00 composes these semantic identities; each domain retains its extension semantics. Kernel CUE expresses semantic objects independently of their file representation: permitted choices, typed values, applicability branches, and the complete slot bindings exposed as `#ProfileSlots`. It does not define a document-root version, a storage container, or a draft-validation entry point. Existing domain contracts still used by other consumers remain their sole authority; their generated CUE projections are deterministic, byte-checked views and do not replace their remaining semantic evaluations.

File encoding, document-root version and packaging, concrete entrypoint names, physical contract-source locations, generation relationships, serialization, interview field mapping, draft-evaluation entry points, and generated presentation belong to Tool. Tool resolves exactly the declared semantic contract identities and supplies its own encoding wrapper separately; changing that wrapper or a physical location does not change a semantic owner. Directory-safe identity spelling and path equality are Tool layout checks; semantic record and extension namespaces remain with their Kernel owner. Human-oriented documentation, interviews, templates, examples, and validator code may consume or project the interface; none creates a second interface or independently copies a referenced owner contract.

## Binding Contract

- A Profile document has one stable Profile identity and binds every registered
  slot exactly once to a Profile-owned structured value. Slot identity remains
  stable when a storage format or presentation changes.
- A binding stays within that Profile and resolves canonically. It cannot borrow
  another Profile, a template, an example, or a repository-root fallback.
- The slot value contains only the adopting repository's stable decision and
  parameters. The Kernel owner named by the interface retains the shared rule;
  Tool capability registries retain implementation identities; runtime state
  retains the current selection and evidence.
- A Profile may reference a stable Read Set, Tool capability, host capability,
  corpus artifact, or adopter-runtime object ID only where the owning extension
  point permits it. A runtime-object reference names the stable object, never
  its current `.cambium` path or value. A reference does not transfer ownership
  of the target.
- `None`, `not-applicable`, `kernel-defaults`, or an inactive registration is a
  complete value only where the interface permits it and the user confirms
  that its condition is true for the repository.
- Unanswered candidate fields remain absent. Absence does not mean inactive,
  confirmed, or adopted. Optional absence represents no binding only where the
  owning branch permits it; a configured branch must supply its required values.
- An independent policy body may remain a referenced Profile-owned text. A
  structured-field reference identifies its semantic target, not a rendered
  heading or copied table. A projection cannot become a second policy owner.

## Confirmation, Validation, And Selection

Templates, interviews, examples, and agents can propose candidate values but cannot confirm them for the user. Mechanical derivations such as an ID-bound path may be generated when they are reproducible from confirmed inputs.

Draft validation checks supplied candidate values against their applicable machine constraints while allowing unanswered fields to remain absent. Complete Profile validation also requires the registered bindings and their owner evaluations. Neither proves semantic quality, user confirmation, or adoption. A directory, successful validation, template, or example never selects a Profile. Selection and its revision history exist only through the Standards adoption operation and belong to adopter runtime state.

## Ownership Boundary

Profile answers do not carry common slot schemas, Kernel defaults, task routes, Read Set membership, Card actions, Tool commands or implementation paths, receipt schemas, state transitions, current Queue or Coverage values, receipts, or recovery history. They may bind stable registered identities only where the owning extension permits them. If a common interface rule must change, its Kernel owner and referenced machine contract change; instance Profiles are then revalidated without becoming owners of that change. For example, K12 owns audit-dimension values even though the Profile interface exposes a slot that binds instance-specific audit extensions. Natural-language predicates retain their semantic owner; Tool does not infer executable rules, policy decisions, or authorization from their text.
