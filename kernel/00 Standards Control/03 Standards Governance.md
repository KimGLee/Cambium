## Navigation

- Parent: [[kernel/00 Standards Overview|00 Standards Overview]].
- Previous: [[kernel/00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]].
- Next: [[kernel/00 Standards Control/04 Control State and Scope|Control State and Scope]].

## Standards Control

| Field | Value |
|---|---|
| Standards version | `{{ release_version }}` |
| Status | `{{ release_status }}` |
| Effective date | `{{ release_effective_date }}` |
| Change authority | User's explicit governance instruction |
| Content-task behavior | Frozen; read-only control plane |

The `{{ ... }}` values above are release placeholders, not values: an adopting instance MUST instantiate them in its first governance release (its initial adoption counts as one), recording the release in the Change Summary below. While the placeholders remain uninstantiated, the composed standard is in pre-release state — content tasks MUST NOT treat it as a frozen Standards version, and a task contract cannot record a frozen `standards_version` from it.

The Standards lifecycle is:

```text
draft
 -> approved
 -> superseded
```

When modifying rules, you MUST:

1. Make explicit that this is a governance change, not ordinary content editing.
2. Record the affected Standards and the reason.
3. Bump `standards_version`.
4. Update the routing and change summary in `00`.
5. Execute the Active-task Adoption of [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]] per the changed-predicate list recorded for the revision; an empty list is a no-op, completed by a one-line adoption receipt.

User approval of the Standards does not equal approval of an immediate bulk Frontmatter migration of all legacy pages. The migration scope still needs to enter a specific task contract.

## Revision Write-back Checklist

Before any Standards revision closes, the following snapshot locations MUST be checked and synchronized; a revision MUST NOT close with write-back incomplete. A revision with no predicate change takes the no-op lightweight path: check only the locations involving the actually modified files; a byte diff + a one-line adoption receipt completes it:

- The state table of [[kernel/00 Standards Control/04 Control State and Scope|Control State and Scope]].
- The Protected Defaults and Task Router of [[kernel/00 Standards Overview|00 Standards Overview]].
- The Module Index of the affected domain MOCs.
- The target lists of the affected Read Sets.
- The [[kernel/00 Standards Control/05 Core Principles and Standards Map#Cross-domain Rule Registry|Cross-domain Rule Registry]].
- Regenerate the affected Runtime Cards through the `Runtime Card Provider` registered by the selected profile; these artifacts (including the provider-resolved index artifact) are all compiled artifacts and must not be hand-edited. Affected = cards whose `source_files` include a modified file. Stamp with `Tools/stamp_cards.py` (`--set-version` synchronizes the version stamp of the provider-resolved index artifact); before the revision closes, `Tools/stamp_cards.py --check` MUST be run and pass.
- Regenerate `Tools/vocab.yaml` (a compiled artifact; the vocabulary owner is each Standard's source text).

Persistent tools self-built by the execution side for gates or audits MUST be brought under Tools/ management through a lightweight governance registration with a designated owner; existing self-built tools are registered retroactively at the next governance pass, and before registration their output is advisory only and MUST NOT serve as a gate's sole evidence.

## Control Accretion Rule

For any revision that adds a check, freeze, invalidation, or reconciliation obligation, the Amendment MUST answer three questions:

1. Which layer currently owns this risk? Why is it insufficient?
2. Which layer owns the new obligation's canonical gate? (Multiple coexisting layers are not allowed.)
3. Is the superseded old layer deleted? If not, why?

If the three questions are not fully answered, the revision MUST NOT pass. Control obligations are managed in the Registry just like content rules.

## Structural Migration Conservation

For any structural migration of the standards corpus (splits, moves, renames, or re-ownership), the following conservation rules apply:

- Every original H2 block MUST have an owner in one and only one leaf module.
- Newly added Navigation, MOCs, and Read Sets do not replace the original rule text.
- When modifying outdated routing, the superseded source text and version status MUST be preserved.
- Apparent duplicates are not deleted during migration; deduplication requires separate governance authorization.
- Corpus-wide heading links MUST be retargeted to the canonical leaf module.
- Path-only links MAY continue to point to the stable domain MOC.
- Before completion, content conservation, Wiki link, heading, table, fence, and routing validation MUST be re-run.

## Leaf Module Size Budget

- Leaf module target ≤5KB, soft cap 6KB.
- When over the limit, cut examples first; if still over, then consider a split, which follows this page's governance change process.
- MOCs and Read Sets have no such limit, but are likewise kept lean.
- Examples default to one good / one bad per rule point.
- Each approved exception MUST register the object, the measured value, the necessity, the growth cap, and the follow-up disposition; the registered cap MUST NOT be exceeded without a new governance change.

| Exception register | Active entries |
|---|---|
| Leaf module exceptions | None; register is open for an authorized governance change |
| Control-plane exceptions | None; register is open for an authorized governance change |

## Execution-Acceptance Ownership Convention

- The `02 Build Execution` domain holds execution principles and trigger points; the `12 Quality Assurance` domain holds acceptance checklists.
- The same item MUST NOT be held in full text on both sides; the execution side references the acceptance side's detail items via Wiki Link and does not copy checklist content.

## Change Summary

Active release register: empty until the first governance change. Each entry MUST record version, date, change, the changed-predicate list, and the Active-task Adoption requirement; when the list is empty, record a no-op adoption receipt.

| Version | Date | Change | Changed predicates | Adoption requirement |
|---|---|---|---|---|
