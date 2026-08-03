## Navigation

- Parent: [[kernel/K07 Sources and Accuracy Standard|K07 Sources and Accuracy Standard]].
- Next: [[kernel/K07 Sources and Accuracy/02 Claims Sources and Classification|Claims Sources and Classification]].

## Purpose

This standard specifies knowledge sources, fact verification, mathematical accuracy, and freshness management, preventing content that looks complete but cannot be verified or is already outdated.

## Source Hierarchy

Priority from high to low:

1. Original papers, formal specifications, standards, and official technical reports.
2. Official documentation, textbooks, and university course materials.
3. Technical articles from authoritative organizations or core maintainers.
4. High-quality secondary explanations, used to aid intuition.
5. Community content, used only to supplement practice experience; it MUST NOT support key conclusions on its own.

Technical questions are checked against primary sources. For protocols, APIs, frameworks, and version behavior, official documentation takes priority.

The source hierarchy answers only "how reliable a source usually is"; it cannot answer "what this source proves in the current argument". Specific source-to-knowledge admission follows the [[kernel/K06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]].

## Source Authority And Evidence Role

Each important source requires judging simultaneously:

- Source authority: whether the author directly owns the data, system, or experimental information.
- Evidence role: whether it is used to discover a problem, explain a mechanism, prove an implementation, provide experiments, show failures, or contradict a conclusion.
- Applicability boundary: which models, tasks, execution / control setups, organizations, and time ranges the conclusion applies to.
- Potential bias: whether vendor promotion, selective disclosure, community survivorship bias, or benchmark incentives are present.

Community content usually has a low authority level, but can be a high-value discovery signal or failure evidence; an official company article can prove its public system, yet cannot automatically prove industry-wide laws (see [[kernel/K07 Sources and Accuracy/03 Official and Cross-source Verification|K07/03]]).

The canonical definitions of the seven evidence roles are in [[kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|K06/03]] Stage 4.
