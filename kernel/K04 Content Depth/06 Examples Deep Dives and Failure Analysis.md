## Navigation

- Parent: [[kernel/K04 Content Depth Standard|K04 Content Depth Standard]].
- Previous: [[kernel/K04 Content Depth/05 Source and Evaluation Depth|Source and Evaluation Depth]].

## Example Standard

Important topics SHOULD include three kinds of examples where possible:

- Minimal example: shows the mechanism with minimal input.
- Real-world example: shows use in a business or production system.
- Failure example: shows misuse, boundaries, or counterexamples.

Mathematical topics need numeric examples; system topics need data flow; risk topics need attack / failure paths.

## Deep-Dive Standard

Each P0 / P1 core topic establishes at least one why-chain of three or more levels:

```text
Why is it needed?
 -> Why does the naive solution fail?
 -> Why does this mechanism help?
 -> Under what assumption does it stop helping?
 -> How would we detect that failure?
```

The body MUST provide the answers; it MUST NOT merely list the questions.

## Failure And Debugging Standard

Writing only generic weaknesses is not acceptable. A Failure Mode SHOULD state:

- Trigger: what conditions trigger it.
- Symptom: what phenomena are observed.
- Root cause: what the underlying cause is.
- Detection: which metrics or logs reveal it.
- Mitigation: how to mitigate it.
- Residual risk: what risk remains.

## Anti-patterns

- Only Definition, Advantages, Disadvantages.
- Every section has only one sentence.
- Repeating the same definition three times with different wording.
- Explaining only the ideal path, without assumptions and failures.
- Formulas only, with no symbol explanation and no numeric examples.
- A flow diagram only, with no explanation of why each step exists.
- Drawing a complex process as a single straight line with no branches, no loops, and no failure paths.
- Merging the proposer's proposal, the gatekeeper's authorization, and the external effect produced by the executor into a single "system executes" step.
- Deleting key transitions, states, or recovery paths to make a diagram fit the viewport.
- Substituting a large number of links for the mechanism explanation the current page should carry.
- An Expression Layer Answer at the end while the body is insufficient to support follow-up questions.
- Compressing a foundation page down to explaining only "how it is used in the current application" to highlight a profile's application mainline.
- Treating an article summary directly as the canonical mechanism explanation.
- A system page with only a component list, without execution, state, coordination, evidence, and recovery paths.

## Related

- [[kernel/K03 Note Types and Ownership Standard|Note Types and Ownership Standard]]
- [[kernel/K07 Sources and Accuracy Standard|Sources and Accuracy Standard]]
- [[kernel/K12 Quality Assurance Standard|Quality Assurance Standard]]
- [[kernel/K06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
