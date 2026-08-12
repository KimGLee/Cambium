# Escalation Policy

Interface: [Escalation Policy slot](../README.md#escalation-policy-slot)

This registry is `None`. That is the minimal legal state of this slot, and a
complete answer rather than a deferral: this profile's only condition for
suspending a task and handing the decision to a person is the kernel trigger —
modifying the Standards or the selected profile requires explicit user
authorization — which
[[kernel/K13 Task Runtime and Execution Control/17 Escalation Policy|K13/17]]
owns and no profile may weaken or restate.

Register a trigger here when this instance runs work long or autonomous enough
that some situation must reach a person before the run continues. The common
ones are an unexempted priority-quota overrun, a replan that changes the
Required set beyond a declared magnitude, a batch left open beyond a declared
age, and any irreversible operation. Each is instance policy: the magnitude and
the age are this corpus's numbers, and belong in the condition cell rather than
in the kernel.

A trigger is not a gate. It emits no receipt and blocks no transition; it
suspends the run and transfers the decision. `check_profile.py` validates the
shape of what is registered below, and whether a fired trigger was honored is a
review question with no automated substitute. What happens on a fired trigger —
`active -> paused` through the sole task-state writer, resume information
saved, the Trigger ID named in the pause record — belongs to
[[kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules|K13/03]]
and is not restated per trigger.

## Escalation Triggers

- Registration: None

| Trigger ID | Condition that fires it | `machine-checkable` or `review-checkable` | Deciding Role ID reference | Resume condition |
|---|---|---|---|---|
