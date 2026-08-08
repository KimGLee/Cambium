## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/14 Card And Read Set Skeleton|Card And Read Set Skeleton]].
- Next: [[kernel/K00 Standards Control/16 Leaf Module Size Register|Leaf Module Size Register]].

## Default Read Sets

Current Read Sets:

- [[kernel/Read Sets/R01 Core Bootstrap Read Set|Core Bootstrap]]: the shared control boundary for all tasks.
- [[kernel/Read Sets/R02 Single Note Authoring Read Set|Single Note Authoring]]: a single canonical note.
- [[kernel/Read Sets/R03 Module Build Read Set|Module Build]]: a complete knowledge module.
- [[kernel/Read Sets/R04 Source-driven Expansion Read Set|Source-driven Expansion]]: external sources and community signals.
- [[kernel/Read Sets/R05 Expression Layer Read Set|R05 Expression Layer]]: creation, migration, and review of expression artifacts; the selected profile supplies the concrete artifact binding and may add supplemental gates.
- [[kernel/Read Sets/R06 Migration and Refactor Read Set|Migration and Refactor]]: moves, renames, splits, and directory restructuring.
- [[kernel/Read Sets/R07 Long-running Execution Read Set|Long-running Execution]]: batch, checkpoint, resume, and Terminal Proof.
- [[kernel/Read Sets/R08 Audit and Completion Read Set|Audit and Completion]]: task completion acceptance and Terminal Audit.
- [[kernel/Read Sets/R09 Standards Governance Read Set|Standards Governance]]: control-plane rule or structure changes.
- [[kernel/Read Sets/R10 Maintenance Run Read Set|Maintenance Run]]: periodic updates and freshness, digesting overdue re-review, watermark deltas, and needs_rereview within the budget envelope.
- [[kernel/Read Sets/R11 Large-scale Work Admission Read Set|Large-scale Work Admission]]: the canonical Large-scale Pre-execution Gate.
- [[kernel/Read Sets/R12 Targeted and Specialized Audit Read Set|Targeted and Specialized Audit]]: bounded review of changed, invalidated, overdue, sampled, or specialized-invariant scope.
- [[kernel/Read Sets/R13 Corpus Planning Read Set|Corpus Planning]]: maintain corpus topology, capability coverage, and semantic-gap admission without taking over content work, Queue execution, or audit.

Together these thirteen Read Sets name every kernel leaf module. A leaf that no loading boundary names cannot be reached by any routed task, so a leaf enters some boundary in the change that creates it. A leaf consulted only when a stated condition appears belongs in that route's `Triggered` boundary; being reachable by one link from a leaf already inside a boundary is not a substitute.

A Runtime Card compiles the boundaries of its own route and owns none of them. So a route that a Card names, in any of its sections, is named by the paired Read Set's boundaries as well. A route reached only from the Card is a load instruction with no boundary behind it: the reader who follows the Card loads it and the reader who resolves the Read Set does not, and the two disagree about what the task read. Either the boundary gains the route or the Card stops naming it, and which of the two is correct is decided by whether the route's work is actually in scope, never by which artifact was easier to edit.

## Derived Load Set

The modules a task loads are derived from the loading boundaries of the Read Sets it selects; that set is resolved, never authored by hand. A declared load set that omits a module a selected boundary names is an under-declaration, and the same two readers disagree again: the one who resolves the boundary loads that module and the one who follows the declaration does not.

A task's selected Read Sets are transitively closed over Read Sets named by their loading boundaries. Every path recorded in `selected_read_sets` MUST prove its role in its own frontmatter: a kernel Read Set uses `type: read-set` under the canonical `kernel/Read Sets/` namespace; a supplemental profile Read Set uses `type: profile-read-set`, remains under the selected Profile directory, and declares a `route_id` present in `selected_profile_route_ids`. Neither type may borrow the other's namespace, and a Profile Read Set from another Profile cannot enter the closure. Ordinary Markdown cannot serve as a traversal root merely because it was placed in the list. Each boundary-referenced Read Set belongs in `selected_read_sets`, and its own loading boundaries are resolved in turn. A cycle selects no Read Set twice and terminates when every selected Read Set has been visited. Every selected or referenced target MUST be a safe repository-contained UTF-8 file; a missing, unsafe, or undecodable target makes the load contract invalid rather than reducing the derived set.

A task's declared load set MUST contain every non-Read-Set target named anywhere in that transitive closure. The obligation is containment, not equality. The declaration MAY additionally name the tools and profile files the selected routes bind, because no loading boundary names those and their absence from the boundaries is not evidence that the task did not need them. What a boundary names is not optional; what no boundary names is not forbidden. `Purpose` states applicability and `Related` supplies navigation, so links in those two sections do not enter either closure. A loading boundary is any Markdown H2 other than those two, including an H2 indented by up to three spaces; fenced code is demonstration text and contributes neither headings nor targets.

A Read Set is recorded by the task's own `selected_read_sets` field and is not duplicated as a module entry. An ordinary index or page does not become a Read Set merely because its path is inside `kernel/Read Sets/`; when a loading boundary names it, it remains a non-Read-Set target and belongs in `loaded_module_paths`.

A declaration is judged when the plan that writes it is admitted. Only a Standards adoption writes a running task's load-set fields, and the plan bytes it wrote them from are then sealed into append-only receipts, so a declaration already written cannot be corrected in place. A frozen contract whose declaration omits a boundary-named target MUST therefore be reported and repaired by the next admitted declaration, and MUST NOT invalidate the runtime holding it: refusing that runtime withholds the one transaction that repairs it. Unresolvable structure is not an under-declaration and has no such escape — a selected path that is missing, unsafe, undecodable, or proves no Read Set type resolves to no closure at all, so it invalidates the load contract wherever it is read.

Which record carries these fields, and how a Standards adoption re-declares them, is owned by [[kernel/K12 Quality Assurance/10 Standards Version Adoption|Standards Version Adoption]] and [[kernel/K12 Quality Assurance/16 Terminal Proof Contract|Terminal Proof Contract]]. What the set must contain is decided here.
