## Navigation

- Parent: [[kernel/06 Knowledge Intake and Evolution Standard|06 Knowledge Intake and Evolution Standard]].
- Next: [[kernel/06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads|User Guidance Hypotheses and Source Leads]].

## Purpose

This standard specifies how external information enters the knowledge base, how it is transformed into verifiable knowledge objects, and when Markdown pages are updated, created, split, merged, deferred, or deprecated.

The problem it solves is not "how to write a summary of an article", but:

```text
外部世界出现新信息后，知识图谱应该发生什么变化？
```

## Scope

This standard applies to:

- Official engineering / research articles from different organizations.
- Papers, benchmarks, technical reports, standards, and protocol updates.
- Production case studies, postmortems, and public architecture write-ups.
- High-quality community discussions, issues, experience summaries, and newly emerging practice problems.
- New gaps in existing knowledge pages exposed by learning, expression tasks, or engineering analysis.

It does not replace the [[kernel/07 Sources and Accuracy Standard|Sources and Accuracy Standard]]. Sources and Accuracy judges whether a conclusion has reliable support; this standard judges how that support should change the knowledge base.

## Core Model

The following objects MUST be distinguished:

```text
Source != Claim != Knowledge Object != Markdown File
```

- A Source is an article, paper, discussion, code, benchmark, or postmortem.
- A Claim is an assertion in a source whose truth and applicability can be judged independently.
- A Knowledge Object is a term, mechanism, component, system, risk, control, or case that requires long-term maintenance.
- A Markdown File is how a knowledge object is carried in the current knowledge base architecture.

A canonical note with the same name MUST NOT be created directly upon seeing a new term or an article title.

## Many-to-many Rule

Sources and knowledge notes have a many-to-many relationship:

- One article can update multiple existing pages and produce multiple new knowledge objects.
- Multiple articles can jointly support one Research Synthesis or canonical note.
- One community discussion can form only a to-be-verified signal, producing no new canonical note.
- A canonical note SHOULD, as far as possible, be supported by multiple independent sources rather than bound to a single vendor narrative.

The knowledge base structure is determined by problems, mechanisms, boundaries, and reuse relationships, not by the directory of article sources.
