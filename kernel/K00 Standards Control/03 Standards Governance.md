## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/02 Task Routing|Task Routing]].
- Next: [[kernel/K00 Standards Control/04 Control State and Scope|Control State and Scope]].

## Standards Control

| Field | Value |
|---|---|
| Standards version | `{{ standards_version }}` |
| Status | `{{ standards_status }}` |
| Effective date | `{{ standards_effective_date }}` |
| Selected profile manifest | `{{ selected_profile_manifest }}` |
| Change authority | User's explicit governance instruction |
| Content-task behavior | Frozen; read-only control plane |

The four `{{ ... }}` entries are placeholders. Initial adoption is the first governance release: fill a copy of `profiles/_template/`; pass `check_profile.py`; record exactly one `profiles/<profile-id>/profile.md`, a version, `approved` status, and date here; record upstream tag, commit, or archive checksum in the Change Summary; compose vocabulary; stamp Cards; pass governance checks. This is adopter state, not Cambium release metadata. Until all four values are instantiated, the standard is pre-release and content tasks cannot freeze a Task Contract.

The Standards lifecycle is:

```text
draft
 -> approved
 -> superseded
```

When modifying rules, you MUST:

1. Make explicit that this is a governance change, not ordinary content editing.
2. Record the affected Standards and the reason.
3. Bump `standards_version`; changing the selected profile manifest always requires a bump.
4. Update the routing and change summary in `K00`.
5. For every existing affected runtime task, publish the changed-predicate input required by [[kernel/K12 Quality Assurance/10 Standards Version Adoption|K12/10]]. R09 owns the governance revision; R07 later executes or resumes the active-task adoption through the sole K13/15 writer. An empty changed-predicate list takes K12/10's no-predicate-change branch rather than bypassing state synchronization.

For an active-task adoption, the restricted-YAML adoption plan is the canonical
machine revision record. Its `governance_revision_ref` must point back to this
file and its SHA-256 must bind these complete approved governance bytes. The
plan additionally binds deterministic after snapshots of the whole `kernel/`
tree and selected Profile directory. Its changed-predicate rows are the
machine-consumed list; the Change Summary remains the governance register and
must agree in meaning, but no second Markdown adoption checklist or copied
revision record is created.

User approval of the Standards does not equal approval of an immediate bulk Frontmatter migration of all legacy pages. The migration scope still needs to enter a specific task contract.

## Revision Write-back Checklist

Before any Standards revision closes, the following snapshot locations MUST be checked and synchronized; a revision MUST NOT close with write-back incomplete. A revision with no predicate change checks only the locations involving the actually modified Standards files. If an existing runtime task is affected, its separate agent-readable adoption plan and controlled state transaction are still required by K12/10; a prose report is never a substitute:

- The state table of [[kernel/K00 Standards Control/04 Control State and Scope|Control State and Scope]].
- The Protected Defaults and Task Router of [[kernel/K00 Standards Overview|K00 Standards Overview]].
- The Module Index of the affected Standard Module MOCs. A leaf module number is never reused once assigned: a retired module leaves a permanent gap, and its Module Index records that the gap is retired rather than missing.
- The target lists of the affected Read Sets.
- The [[kernel/K00 Standards Control/11 Standards Map and Rule Registry#Cross-domain Rule Registry|Cross-domain Rule Registry]].
- The measured values and dispositions of [[kernel/K00 Standards Control/16 Leaf Module Size Register|Leaf Module Size Register]], for every leaf module the revision changed in size. `Tools/stamp_cards.py --check` reports both, so this location is checked by the same run as the Cards below.
- Regenerate the affected kernel Runtime Cards under `kernel/Cards`; these artifacts, including the Card Index, are compiled artifacts and must not be hand-edited outside this write-back step. Affected = cards whose `source_files` include a modified file. `source_files` contains the direct semantic inputs from which Card guidance is compiled; a file linked only as a runtime read-back or navigation target is not added solely because of that link, whose reachability is checked separately. Stamp with `Tools/stamp_cards.py` (`--set-version` synchronizes every card's version stamp); before the revision closes, `Tools/stamp_cards.py --check` MUST be run and pass. A missing card directory, missing Card Index, missing Read Set mapping, or zero-card scan is a failure, never `not_applicable`.
- Regenerate `Tools/vocab.yaml` only when the adopting instance has selected a profile and the revision changes the selected profile, the kernel vocabulary base, or that profile's `Vocabulary Extensions` binding or content. The artifact is compiled from the active selection and those inputs; the generic Cambium distribution and an instance with no selected profile carry no composed vocabulary.

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
- Path-only links MAY continue to point to the stable Standard Module MOC.
- Before completion, content conservation, Wiki link, heading, table, fence, and routing validation MUST be re-run.

## Leaf Module Size Budget

- Leaf module target ≤5KB, soft cap 6KB; KB means 1024 bytes.
- The cap applies by function, not by folder or file type. It applies to a page that owns rule text: a task that needs one of its rules reads the page whole, so the page's size is what reaching that rule costs.
- A page that owns no rule text is outside the cap, because every normative sentence in it points to a rule owned elsewhere (Core Principle 20), and splitting such a page raises resolution cost instead of lowering it. Standard Module MOCs, Read Sets, and the standards maps and registries are the usual cases. These pages are likewise kept lean.
- Being outside the cap and being a registered exception are exclusive dispositions; a page outside the cap is not registered below.
- When over the limit, cut examples first; if still over, then consider a split, which follows this page's governance change process. An example that illustrates a rule the page states MAY be cut. An example a reader needs in order to decide which of the page's rules applies to the case in hand is doing the page's work rather than illustrating it: it is not cut, and the page goes straight to the split test.
- Examples default to one good / one bad per rule point.
- Each approved exception MUST register the object, the measured value, the necessity, the growth cap, and the follow-up disposition; the registered cap MUST NOT be exceeded without a new governance change.
- The register of approved exceptions is carried by [[kernel/K00 Standards Control/16 Leaf Module Size Register|Leaf Module Size Register]]; it holds no rule of its own and is outside this cap.
- A leaf module over the soft cap carries exactly one of the two dispositions in that register: an approved exception, or an outside-the-cap declaration giving the reason it owns no rule text. An undeclared page over the soft cap is a candidate, not a failure; the soft cap is soft, and only a registered growth cap is a MUST. `Tools/stamp_cards.py` measures every leaf against this budget and that register.

## Execution-Acceptance Ownership Convention

- The `K02 Knowledge Work Construction` standard module holds knowledge-work principles and trigger points; `K13 Task Runtime and Execution Control` holds persistent state and transitions; the `K12 Quality Assurance` standard module holds acceptance checklists.
- The same item MUST NOT be held in full text on both sides; the execution side references the acceptance side's detail items via Wiki Link and does not copy checklist content.

## Change Summary

The upstream register is empty; initial adoption creates its first entry. Each entry MUST record version, date, change (including profile selection and upstream provenance when applicable), changed predicates, and the IDs of any active-task adoption plans it requires. An empty predicate list selects K12/10's no-predicate-change branch; it does not authorize direct runtime-state edits.

| Version | Date | Change | Changed predicates | Adoption requirement |
|---|---|---|---|---|
