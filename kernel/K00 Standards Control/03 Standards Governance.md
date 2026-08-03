## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]].
- Next: [[kernel/K00 Standards Control/04 Control State and Scope|Control State and Scope]].

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
4. Update the routing and change summary in `K00`.
5. Execute the Active-task Adoption of [[kernel/K12 Quality Assurance/10 Standards Version Adoption|K12/10]] per the changed-predicate list recorded for the revision; an empty list is a no-op, completed by a one-line adoption receipt.

User approval of the Standards does not equal approval of an immediate bulk Frontmatter migration of all legacy pages. The migration scope still needs to enter a specific task contract.

## Revision Write-back Checklist

Before any Standards revision closes, the following snapshot locations MUST be checked and synchronized; a revision MUST NOT close with write-back incomplete. A revision with no predicate change takes the no-op lightweight path: check only the locations involving the actually modified files; a byte diff + a one-line adoption receipt completes it:

- The state table of [[kernel/K00 Standards Control/04 Control State and Scope|Control State and Scope]].
- The Protected Defaults and Task Router of [[kernel/K00 Standards Overview|K00 Standards Overview]].
- The Module Index of the affected Standard Module MOCs.
- The target lists of the affected Read Sets.
- The [[kernel/K00 Standards Control/11 Standards Map and Rule Registry#Cross-domain Rule Registry|Cross-domain Rule Registry]].
- Regenerate the affected kernel Runtime Cards under `kernel/Cards`; these artifacts, including the Card Index, are compiled artifacts and must not be hand-edited outside this write-back step. Affected = cards whose `source_files` include a modified file. Stamp with `Tools/stamp_cards.py` (`--set-version` synchronizes every card's version stamp); before the revision closes, `Tools/stamp_cards.py --check` MUST be run and pass. A missing card directory, missing Card Index, missing Read Set mapping, or zero-card scan is a failure, never `not_applicable`.
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
| Leaf module exceptions | 8 active; registered below |
| Control-plane exceptions | None; register is open for an authorized governance change |

| Leaf module exception | Measured | Necessity | Growth cap | Follow-up |
|---|---|---|---|---|
| [[kernel/K00 Standards Control/03 Standards Governance\|Standards Governance]] (this page) | 14293 bytes | Its only routed consumer is the Standards Governance Read Set, which reads it at Start; one governance change consults the change process, the write-back checklist, the accretion questions, the migration conservation rules, and this budget in a single pass. The one other reader, the batch-activation version self-check of [[kernel/K00 Standards Control/02 Task Routing and Pre-execution\|K00/02]], takes one scalar from the Standards Control table rather than loading the page, and splitting that table out would make every governance change read both halves | 14.5KB | Re-measure at each governance change. No section of this page has a standalone consumer: no page links any of its seven headings, and its only routed consumer reads it whole. Its size therefore grows almost entirely with the register below, which gains a row per approved exception, so raising this cap is a recurring cost rather than a one-time one. Before the next raise, the register MUST first be tested against the outside-the-cap disposition above, which covers registries that own no rule text; the register moves out the first time that test or the split test passes |
| [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract\|Completion Precedence and Task Contract]] | 6447 bytes | Splitting saves no reader. All four anchored readers of its sections sit inside tasks that already hold the whole page, because [[kernel/Read Sets/R01 Core Bootstrap Read Set\|Core Bootstrap]] reads it at Start for every task. `Maintenance Completion` further MUST stay with `Definition Of Complete`: the page requires one of the two to be declared when the task contract is frozen and forbids mixing their semantics, so a task holding one half could not make that declaration | 7KB | Re-measure whenever a contract decision or a completion semantic is added; the split condition is a routed consumer that resolves standard precedence without holding a task contract |
| [[kernel/K02 Build Execution/02 Mid-task Guidance and Amendment\|Mid-task Guidance and Amendment]] | 10158 bytes | One event-triggered procedure. A single guidance event runs classification, impact analysis, disposition, safe switching, the amendment record, versioning, and acknowledgement in one pass, and no consumer reaches a part of it alone: both anchored readers, [[kernel/K12 Quality Assurance/04 Guidance and Source Review\|K12/04]] and [[kernel/K06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads\|K06/02]], link the whole `Mid-task Guidance And Contract Amendment` section, and no Read Set routes to a subsection | 10.5KB | Re-measure whenever a guidance class, a disposition, or an amendment field is added; the split condition is a routed consumer that records an amendment without having classified the guidance that caused it |
| [[kernel/K03 Note Types and Ownership/01 Note Type Catalog\|Note Type Catalog]] | 6668 bytes | One catalog whose function is choosing among its sixteen types. Both routed consumers, the Single Note Authoring and Module Build Read Sets, load it for that same choice, and no page links an individual type, so a split by type group would make every choice read both groups | 7KB | Re-measure whenever a note type is added. Its seven `Examples:` lines (561 bytes) were tested against the cut-examples remedy and held: they are what a reader compares against to decide which of the sixteen types a page is, so cutting them would remove the judgment the catalog exists to support. The split condition is a routed consumer that already knows its type group before opening the catalog |
| [[kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline\|Source-to-Knowledge Pipeline]] | 7443 bytes | Its two externally entered gates are already extracted to [[kernel/K06 Knowledge Intake and Evolution/07 Environmental Scanning and Watermark\|K06/07]] and [[kernel/K06 Knowledge Intake and Evolution/08 Canonical Promotion Gate\|K06/08]], which are the only stages a consumer enters on its own. What remains is one traversal: Stages 2-8 and 10 have no meaning without the stages before them, and both routed consumers, the Source-driven Expansion Read Set at Start and the Source-driven Expansion Batch of [[kernel/K02 Build Execution/05 Batch Execution\|K02/05]] which requires Stage 1-10 in full, run them in order in a single pass | 7.5KB | Re-measure whenever a stage is added; the next split MUST be a stage a consumer can enter on its own, as K06/07 and K06/08 were, never a range of the traversal |
| [[kernel/K12 Quality Assurance/05 Automated and Manual Checks\|Automated and Manual Checks]] | 6823 bytes | Its three sections are one classification of the same finding: what a script decides, what a domain rule decides, and what still needs a person. All five routed consumers load it at their Gate to place a finding among the three, no page links a section of it, and separating them would leave each part deferring to the others for the findings it does not cover | 7KB | Re-measure whenever a check is added; the split condition is a routed consumer that classifies a finding as automated without needing to know whether the manual path applies |
| [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation\|Audit Evidence Reuse and Invalidation]] | 14624 bytes | Its three separable tenants are already extracted to [[kernel/K12 Quality Assurance/09 Batch-close Closed List\|K12/09]], [[kernel/K12 Quality Assurance/10 Standards Version Adoption\|K12/10]], and [[kernel/K12 Quality Assurance/11 Content-level Propagation\|K12/11]]. What remains answers one question — may this run reuse the receipt it holds, or must it recompute — and no routed consumer reaches a part of it alone: the receipt schema is unreadable without the audit layers it is keyed by, and the Reuse Gate and Invalidation are the two halves of that one answer, so separating them would leave each half deferring to the other | 15KB | Re-measure whenever an audit layer or a receipt dimension is added; the next split MUST be a whole tenant with its own routed consumer, never a section of the reuse decision |
| [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map\|Judgment Item Dimension Map]] | 8652 bytes | The module is one lookup table plus the rules for reading it, and it carries no examples to cut. Its reverse check — that every base receipt dimension has at least one emitting item — is performed by reading a single table, and any split removes that property | 8.5KB | Re-measure whenever the kernel's judgment item set changes; if the cap is reached, split by audit layer rather than by section, and restate the reverse check in both halves |
## Execution-Acceptance Ownership Convention

- The `K02 Build Execution` standard module holds execution principles and trigger points; the `K12 Quality Assurance` standard module holds acceptance checklists.
- The same item MUST NOT be held in full text on both sides; the execution side references the acceptance side's detail items via Wiki Link and does not copy checklist content.

## Change Summary

Active release register: empty until the first governance change. Each entry MUST record version, date, change, the changed-predicate list, and the Active-task Adoption requirement; when the list is empty, record a no-op adoption receipt.

| Version | Date | Change | Changed predicates | Adoption requirement |
|---|---|---|---|---|
