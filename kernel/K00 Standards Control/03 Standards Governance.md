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
- The Module Index of the affected Standard Module MOCs.
- The target lists of the affected Read Sets.
- The [[kernel/K00 Standards Control/11 Standards Map and Rule Registry#Cross-domain Rule Registry|Cross-domain Rule Registry]].
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

- Leaf module target ≤5KB, soft cap 6KB.
- The cap applies by function, not by folder or file type. It applies to a page that owns rule text: a task that needs one of its rules reads the page whole, so the page's size is what reaching that rule costs.
- A page that owns no rule text is outside the cap, because every normative sentence in it points to a rule owned elsewhere (Core Principle 20), and splitting such a page raises resolution cost instead of lowering it. Standard Module MOCs, Read Sets, and the standards maps and registries are the usual cases. These pages are likewise kept lean.
- Being outside the cap and being a registered exception are exclusive dispositions; a page outside the cap is not registered below.
- When over the limit, cut examples first; if still over, then consider a split, which follows this page's governance change process. An example that illustrates a rule the page states MAY be cut. An example a reader needs in order to decide which of the page's rules applies to the case in hand is doing the page's work rather than illustrating it: it is not cut, and the page goes straight to the split test.
- Examples default to one good / one bad per rule point.
- Each approved exception MUST register the object, the measured value, the necessity, the growth cap, and the follow-up disposition; the registered cap MUST NOT be exceeded without a new governance change.

| Exception register | Active entries |
|---|---|
| Leaf module exceptions | 6 active; registered below |
| Control-plane exceptions | None; register is open for an authorized governance change |

| Leaf module exception | Measured | Necessity | Growth cap | Follow-up |
|---|---|---|---|---|
| [[kernel/K00 Standards Control/03 Standards Governance\|Standards Governance]] (this page) | 14568 bytes | R09 reads the whole page for a governance change; R01 reads only Standards Control to resolve the active version and profile. Keeping state with its change process prevents a governance revision from updating one without the other | 14.5KB | Re-measure at each governance change. Split when a routed consumer needs active state without R01 or the governance process; move this exception registry when it passes the outside-the-cap test |
| [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract\|Completion Precedence and Task Contract]] | 7149 bytes | Splitting saves no reader. All four anchored readers of its sections sit inside tasks that already hold the whole page, because [[kernel/Read Sets/R01 Core Bootstrap Read Set\|Core Bootstrap]] reads it at Start for every task. `Maintenance Completion` further MUST stay with `Definition Of Complete`: the page requires one of the two to be declared when the task contract is frozen and forbids mixing their semantics, so a task holding one half could not make that declaration | 7KB | Re-measure whenever a contract decision or a completion semantic is added; the split condition is a routed consumer that resolves standard precedence without holding a task contract |
| [[kernel/K03 Note Types and Ownership/01 Note Type Catalog\|Note Type Catalog]] | 6668 bytes | One catalog whose function is choosing among its sixteen types. Both routed consumers, the Single Note Authoring and Module Build Read Sets, load it for that same choice, and no page links an individual type, so a split by type group would make every choice read both groups | 7KB | Re-measure whenever a note type is added. Its seven `Examples:` lines (561 bytes) were tested against the cut-examples remedy and held: they are what a reader compares against to decide which of the sixteen types a page is, so cutting them would remove the judgment the catalog exists to support. The split condition is a routed consumer that already knows its type group before opening the catalog |
| [[kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline\|Source-to-Knowledge Pipeline]] | 7443 bytes | Its two externally entered gates are already extracted to [[kernel/K06 Knowledge Intake and Evolution/07 Environmental Scanning and Watermark\|K06/07]] and [[kernel/K06 Knowledge Intake and Evolution/08 Canonical Promotion Gate\|K06/08]], which are the only stages a consumer enters on its own. What remains is one traversal: Stages 2-8 and 10 have no meaning without the stages before them, and both routed consumers, the Source-driven Expansion Read Set at Start and the Source-driven Expansion Batch of [[kernel/K02 Knowledge Work Construction/09 Knowledge Batch Production\|K02/09]] which requires Stage 1-10 in full, run them in order in a single pass | 7.5KB | Re-measure whenever a stage is added; the next split MUST be a stage a consumer can enter on its own, as K06/07 and K06/08 were, never a range of the traversal |
| [[kernel/K12 Quality Assurance/05 Automated and Manual Checks\|Automated and Manual Checks]] | 7006 bytes | Its three sections are one classification of the same finding: what a script decides, what a domain rule decides, and what still needs a person. All five routed consumers load it at their Gate to place a finding among the three, no page links a section of it, and separating them would leave each part deferring to the others for the findings it does not cover | 7KB | Re-measure whenever a check is added; the split condition is a routed consumer that classifies a finding as automated without needing to know whether the manual path applies |
| [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation\|Audit Evidence Reuse and Invalidation]] | 15668 bytes | Its three separable tenants are already extracted to [[kernel/K12 Quality Assurance/09 Batch-close Closed List\|K12/09]], [[kernel/K12 Quality Assurance/10 Standards Version Adoption\|K12/10]], and [[kernel/K12 Quality Assurance/11 Content-level Propagation\|K12/11]]. What remains answers one question — may this run reuse the receipt it holds, or must it recompute — and no routed consumer reaches a part of it alone: the receipt schema is unreadable without the audit layers it is keyed by, and the Reuse Gate and Invalidation are the two halves of that one answer, so separating them would leave each half deferring to the other | 15.5KB | Re-measure whenever an audit layer or a receipt dimension is added; the next split MUST be a whole tenant with its own routed consumer, never a section of the reuse decision |

This registry no longer carries [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]]. Its registered follow-up was executed: the map was split by audit layer into K12/08 for the Single Note Review layer and [[kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map|K12/18]] for the layers above one page and the control-plane Gates, with the reverse check restated in both halves — owned by K12/08, carried in K12/18 as a declared derived view. Both halves measure inside the 6KB soft cap, so neither is registered here.

## Execution-Acceptance Ownership Convention

- The `K02 Knowledge Work Construction` standard module holds knowledge-work principles and trigger points; `K13 Task Runtime and Execution Control` holds persistent state and transitions; the `K12 Quality Assurance` standard module holds acceptance checklists.
- The same item MUST NOT be held in full text on both sides; the execution side references the acceptance side's detail items via Wiki Link and does not copy checklist content.

## Change Summary

The upstream register is empty; initial adoption creates its first entry. Each entry MUST record version, date, change (including profile selection and upstream provenance when applicable), changed predicates, and the IDs of any active-task adoption plans it requires. An empty predicate list selects K12/10's no-predicate-change branch; it does not authorize direct runtime-state edits.

| Version | Date | Change | Changed predicates | Adoption requirement |
|---|---|---|---|---|
