## Navigation

- Parent: [[kernel/K13 Task Runtime and Execution Control Standard|K13 Task Runtime and Execution Control Standard]].
- Previous: [[kernel/K13 Task Runtime and Execution Control/16 Resume Next Action Vocabulary|Resume Next Action Vocabulary]].
- Next: [[kernel/K13 Task Runtime and Execution Control/18 Initial Task Planning Transaction|Initial Task Planning Transaction]].

## Purpose And Boundary

This module owns one object: the **escalation contract** — the declared
conditions under which an executor MUST suspend the task and hand the decision
to the `stopper`, and what counts as the decision that permits resuming.

It owns the class, one kernel-owned trigger, and the extension point. It does
not own the `paused` state or its transitions
([[kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules|K13/03]]),
the resume token
([[kernel/K13 Task Runtime and Execution Control/16 Resume Next Action Vocabulary|K13/16]]),
or the role vocabulary
([[kernel/K04 Content Depth/03 Process and Flow Structure|K04/03]], bound by
the selected profile's `Role Registry`).
[[kernel/K12 Quality Assurance/13 Visual Verification Escalation|K12/13]] uses
the same word for a different object: that is an evidence-tier escalation
inside a check, not a handover of the run.

## The Kernel Trigger

Modifying the Standards or the selected profile requires explicit user
authorization before the change is made. This trigger is constitutional: a
profile may neither relax nor remove it.
[[kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis|K13/04]]
routes a Governance candidate to it,
[[kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning|K13/06]]
binds it to `standards_version`, and the R09 Card carries it as a checklist
item compiled from this owner. Those are applications of one rule at the three
points where it fires, not three rules.

## Profile-declared Triggers

Every further condition is instance policy, registered in the selected
profile's `Escalation Policy` slot. A registration may only add; it cannot
weaken the kernel trigger, and it cannot register a condition already owned by
a gate. Each registration declares:

| Field | Meaning |
|---|---|
| Trigger ID | `lower_snake_case`, unique within the profile |
| Condition | What must hold for the trigger to fire, marked `machine-checkable` or `review-checkable` |
| Deciding role | A Role ID from `Role Registry`; usually `stopper` |
| Resume condition | What counts as the decision having been made |

A profile that registers nothing declares that explicitly. Registering nothing
is a complete answer for a bounded task whose only stop condition is the kernel
trigger; it is not a deferral.

## Firing And Resuming

On a fired trigger the executor records `active -> paused` through
`Tools/update_task.py` with resume information saved, names the Trigger ID in
the pause record, and starts no new Required work. In-flight batch work
reaches a checkpoint rather than being abandoned. Resuming requires that
trigger's registered resume condition to hold; the run then follows the
`resume-paused-task` token.

A trigger fires on its condition, not on the executor's confidence. An
executor that judges the condition met and proceeds anyway has broken this
contract even when the outcome is good.

## A Trigger Is Not A Gate

A gate judges an artifact against a predicate and emits a receipt; a failed
gate blocks a transition. A trigger judges the run's situation and transfers
the decision to a person; it emits no receipt and blocks nothing by itself.

No checker fires on a trigger. `check_profile.py` validates the registration's
shape as part of `profile-load`; whether an executor honored a fired trigger is
a review question with no automated substitute. This boundary is stated rather
than left implicit because an obligation with no defined disposition when it is
not met is how a private ritual begins — the executor improvises a
consequence, and the improvised direction is rarely the correct one.

## Control Accretion Decision

Which layer owned this risk, and why was it insufficient? No layer owned it.
The kernel trigger was stated at each of its three application points with no
owner naming the class, and every other condition an instance needs — an
unexempted quota overrun, a replan beyond a declared magnitude, a batch idle
beyond a declared age, an irreversible operation — had nowhere to live. K13/03
owns `paused`, but `stopped by request` describes a human-initiated stop; the
executor-initiated case and its conditions had no owner, so each adopter
invented one outside the corpus, where it drifted out of step with the kernel
that had meanwhile grown machine enforcement for parts of it.

Which layer owns the new obligation's canonical gate? None, and that is the
answer rather than an omission: this obligation has no gate by construction,
per the section above. The rule owner is this module; the registration's shape
is validated by the `profile-load` Gate, whose owner remains
[[kernel/K00 Standards Control/17 Profile Dependency Closure|K00/17]].

Is the superseded old layer deleted? Nothing is deleted, because nothing is
superseded. K13/04 and K13/06 keep their statements — they are where the
kernel trigger fires — and gain a pointer to this owner. What changes is that
a scattered, unnamed obligation acquires a name, a single owner, and an
extension point an adopter can use instead of improvising outside the corpus.

## Related

- [[kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules|Task State and Transition Rules]]
- [[kernel/K13 Task Runtime and Execution Control/16 Resume Next Action Vocabulary|Resume Next Action Vocabulary]]
- [[kernel/K04 Content Depth/03 Process and Flow Structure|Process and Flow Structure]]
