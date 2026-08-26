# Profile Template

This directory is a copyable candidate form for the Kernel-owned Profile
interface. It is not a Profile, is not selectable in place, and has no
governance authority. The normative slot set and its Kernel owners are in
[`kernel/K00 Standards Control/profile-interface.yaml`](../../kernel/K00%20Standards%20Control/profile-interface.yaml).

Create a candidate with:

```sh
python3 Tools/scaffold_profile.py . --profile-id <profile-id>
python3 Tools/scaffold_profile.py . --profile-id <profile-id> --apply
```

The scaffolder copies only the files listed in
[`profiles/template-files.yaml`](../template-files.yaml), excludes this
orientation README, and derives values that are pure functions of the chosen
Profile ID. It does not answer any semantic question or select the result.

Use [`profiles/interview.yaml`](../interview.yaml) and
[`profiles/answer-patterns.md`](../answer-patterns.md) while discussing the
repository with the user. Every unresolved profile placeholder needs a
confirmed answer.
Pre-filled inactive choices and candidate policies also require confirmation;
replace them whenever their stated condition is not true for the repository.

After the conversation, validate only the mechanical contract:

```sh
python3 Tools/check_profile.py profiles/<profile-id>
```

A successful check proves structure and reference consistency. It does not
prove semantic quality, user confirmation, or adoption. Selection occurs only
through the Standards adoption operation, whose current result is stored in
the adopter's `.cambium/` state.
