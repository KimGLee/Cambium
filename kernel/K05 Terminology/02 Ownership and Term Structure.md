## Navigation

- Parent: [[kernel/K05 Terminology Standard|K05 Terminology Standard]].
- Previous: [[kernel/K05 Terminology/01 Terminology Extraction|Terminology Extraction]].
- Next: [[kernel/K05 Terminology/03 Naming Context and Linking|Naming Context and Linking]].

## Ownership

Terminology uses the "lowest reasonable ownership" rule:

1. Clear domain ownership: place it in that domain.
2. Reused across multiple domains with a foundation-discipline home: place it in the `Shared Foundation Layer` registered by the selected profile.
3. Generic to production systems: place it in the `Production Systems Layer` registered by the selected profile.
4. Truly cross-domain with no natural owner: place it in the `Cross-domain Concepts Layer` registered by the selected profile.
5. The expression layer does not change a term's owner; the `Expression Layer Artifact` only references it.

Creating an uncategorized, unboundedly growing global Glossary folder is not recommended.

## Suggested Structure

The concrete directory tree is registered by the selected profile's `Profile Scope` under `Terminology Structure`.

This structure is to be created only after the overall architecture is confirmed; the current rule does not automatically move existing term pages.

## Term Note Structure

A complete Term Note usually contains:

```text
Full Name And Aliases
Definition
Why This Term Exists
Intuition
Formal Meaning
Notation / Data Structure
Minimal Example
Where It Is Used
What It Is Not
Common Misconceptions
Expression Layer Link
Related Terms
Sources
```

When mathematics is involved, add formulas; when systems are involved, add inputs, outputs, and lifecycle; when protocols are involved, add roles, boundaries, and version information.
