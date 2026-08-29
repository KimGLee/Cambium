# Profile

A Profile is the set of customized governance requirements that a user has chosen and confirmed for one knowledge repository. It binds the extension points opened by the Kernel; it does not restate or weaken Kernel rules.

The common slot interface is owned by [`kernel/K00 Standards Control/profile-interface.yaml`](../kernel/K00%20Standards%20Control/profile-interface.yaml). This README, the interview, and the template are guidance surfaces rather than additional interface authorities. The interface references K12's [`audit-dimension-base.yaml`](../kernel/K12%20Quality%20Assurance/audit-dimension-base.yaml) for the common audit-dimension and evidence-role values; an instance Profile may bind permitted extensions but does not own that base namespace.

## What belongs in a Profile

A selected Profile may hold stable, repository-specific choices such as scope, logical directories, language, terminology, sources, priority predicates, role bindings, review predicates, and enabled Kernel extensions. It may also hold stable references to Read Sets, Tool capabilities, host capabilities, or corpus artifacts without taking ownership of their contents, implementation, or current state.

A Profile does not hold Kernel defaults, common slot schemas, Card steps, Read Set membership, Tool implementation details, task-time choices, Queue or Coverage data, receipts, recovery data, or adoption history. Current selection and execution evidence belong under `.cambium/`.

## Candidate creation

Start a candidate with the exact-copy scaffolder:

```sh
python3 Tools/scaffold_profile.py . --profile-id my-profile
python3 Tools/scaffold_profile.py . --profile-id my-profile --apply
```

Then use [`interview.yaml`](interview.yaml) and [`answer-patterns.md`](answer-patterns.md) to discuss the repository's actual needs with the user. Replace every `TODO(profile)` only with a confirmed answer. Inactive forms such as `None`, `not-applicable`, or `kernel-defaults` are decisions too; they must not be silently accepted from the template.

The sole copyable candidate template lives in [`_template/`](_template/). The exact copied file set is declared by [`template-files.yaml`](template-files.yaml); the template's README is orientation and is deliberately not copied. Answer depth is determined during the user interview, not by selecting another template directory.

## Mechanical validation and adoption

Validate a filled candidate with:

```sh
python3 Tools/check_profile.py profiles/my-profile
```

Validation proves only mechanical matters such as shape, allowed values, identity, reference closure, and machine consistency. It does not prove that the answers are appropriate, that the user confirmed them, or that the Profile has been adopted.

A directory, valid manifest, template, or example never becomes active merely by existing. A Profile is selected only by the Standards adoption operation; the selected identity and its history are adopter runtime state under `.cambium/`.

For the full Profile boundary, see the repository's Cambium Constitution. For the semantics of any slot, follow its `kernel_owner` entry in the Kernel-owned interface registry.
