# System And Project Deep Dive

## Applicability

This module applies to every System Design Card and Project Deep Dive Card. A Concept Card uses it only when the Card claims an end-to-end system, production result, or personal project outcome.

## System Deep-dive Evidence Chain

A System Design Card covers each applicable item and marks a genuinely inapplicable item explicitly:

1. problem and measurable success criteria;
2. why an agent is needed and what the harness controls;
3. end-to-end execution path;
4. state ownership, persistence, and artifact boundaries;
5. coordination and handoff behavior;
6. tool, permission, and policy boundaries;
7. evaluation provenance and authoritative outcome evidence;
8. replay, regression, or backtesting strategy;
9. failure propagation, retry, rollback, and recovery;
10. observability and incident diagnosis;
11. latency, cost, capacity, and scale;
12. alternatives and rejected designs.

## Project Deep-dive Evidence Chain

A Project Deep Dive Card distinguishes verified project facts from the speaker's inference and covers:

- the business or user problem and the speaker's bounded responsibility;
- the initial constraints, baseline, and success measure;
- the architecture decision and rejected alternatives;
- the execution and evaluation artifacts supporting reported metrics;
- deployment, monitoring, failure, recovery, and follow-up changes;
- what the result does not prove and what would be improved next.

A source note or public case cannot be presented as personal project evidence. Quantitative claims remain traceable through the evaluation-provenance requirements in the profile's [[profiles/examples/agent-atlas/source-policy#Provenance Extensions|Source Policy]].

## Bilingual Answer Contract

The 30-second and 90-second answers are complete in both English and Chinese. Follow-up prompts use bilingual labels, and every follow-up intended for spoken delivery includes an English answer or a usable English answer skeleton. The two language versions preserve the same claim, limitation, uncertainty, and metric meaning.

This section owns only Interview Card answer parity. General body language, naming, display order, protected identifiers, and formatting remain owned by the profile's [[profiles/examples/agent-atlas/language-contract|Language Contract]].
