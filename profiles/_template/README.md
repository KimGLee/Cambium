# Profile Template

This directory is a copyable candidate form for the Kernel-owned Profile interface. It is not a Profile, is not selectable in place, and has no governance authority. The normative slot set and its Kernel owners are in [`kernel/K00 Standards Control/profile-interface.yaml`](../../kernel/K00%20Standards%20Control/profile-interface.yaml).

Create a candidate with:

```sh
python3 Tools/scaffold_profile.py . --profile-id <profile-id>
python3 Tools/scaffold_profile.py . --profile-id <profile-id> --apply
```

The scaffolder copies only the files listed in [`profiles/template-files.yaml`](../template-files.yaml), excludes this orientation README, and derives values that are pure functions of the chosen Profile ID. It does not answer any semantic question or select the result.

Use [`profiles/interview.yaml`](../interview.yaml) and [`profiles/answer-patterns.md`](../answer-patterns.md) while discussing the repository with the user. Every unresolved profile placeholder needs a confirmed answer. Pre-filled inactive choices and candidate policies also require confirmation; replace them whenever their stated condition is not true for the repository.

## Form And Answer Boundary

The sixteen copied files are the candidate Profile's answer record, not its filling instructions. Keep only confirmed instance values, inactive registrations, typed tables, and the Kernel-owner references in that copy. Questions such as whether to keep a pre-fill, how to choose a stable ID, or when to open an extension belong in the interview; reusable answer shapes belong in `answer-patterns.md`.

The template deliberately pre-fills several valid inactive or small-corpus values. They are proposals, not automatic decisions. During the interview:

- confirm or replace every pre-filled `None`, `not-applicable`, `kernel-defaults`, naming row, role binding, and policy value;
- replace every `TODO(profile)` with the user's confirmed repository-specific answer;
- use exact repository-relative paths and stable IDs in typed fields;
- keep `## Artifact Contracts` as the landing section for Profile-owned artifact contracts, with each registered artifact row pointing to its exact contract heading;
- name the real volatility domains used by the corpus instead of retaining `general` by accident; and
- record reader-facing `sources` and `related` titles and any bounded aliases only in Metadata Contract `section_roles`; do not duplicate that machine mapping in Language Contract.

For an existing corpus, observed naming and headings are the starting evidence. A different confirmed value can imply migration work; filling the Profile must not silently rename corpus content.

After the conversation, validate only the mechanical contract:

```sh
python3 Tools/check_profile.py profiles/<profile-id>
```

A successful check proves structure and reference consistency. It does not prove semantic quality, user confirmation, or adoption. Selection occurs only through the Standards adoption operation, whose current result is stored in the adopter's `.cambium/` state.
