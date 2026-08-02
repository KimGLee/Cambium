## Navigation

- Parent: [[kernel/03 Note Types and Ownership Standard|03 Note Types and Ownership Standard]].
- Previous: [[kernel/03 Note Types and Ownership/02 Ownership and Canonical Notes|Ownership and Canonical Notes]].

## Purpose

This module is the canonical owner of the page lifecycle policy (Split Merge and Retirement Policy), covering split, merge, and retirement. The file name stays unchanged to avoid breaking links.

## When To Split A Note

Consider splitting when the following apply:

- The subtopic is reused by multiple pages.
- The subtopic has an independent mechanism, formula, lifecycle, or failure mode.
- The current page drifts off its mainline because it explains this subtopic.
- The subtopic can generate independent learning questions or expression questions registered by the selected profile.
- After the split, coherence can still be maintained through an explicit continuation relationship.
- A new source reveals multiple independent knowledge objects with different owners.

## When Not To Split

- Only one ordinary definition sentence.
- Used only on the current page.
- The new page would contain only two or three sentences after the split.
- The subtopic can only be understood by depending on the current page's context.
- The split is only to increase graph nodes or file count.
- It is only a temporary label used by one article and has not yet been shown to have a stable, reusable meaning.

## Duplication Policy

Duplication is allowed:

- A one-sentence contextual explanation provided to keep a paragraph readable.
- The minimal necessary definition within a length-limited expression.
- A brief restatement of decision background in a Case Study.
- A minimal claim summary in a Research Synthesis for comparing sources.

Duplication is not allowed:

- Multiple pages copying the same full mechanism explanation.
- Multiple profile expression artifacts storing the same complete answer.
- A Roadmap or Cheat Sheet rewriting the body of a knowledge page.
- Creating effectively identical concept pages by renaming.

## Retirement

Retirement does not delete files:

- Set `lifecycle: retired` in the frontmatter.
- Add a tombstone block at the top of the body: retirement reason, retirement date, a `superseded_by` link pointing to the successor page; when there is no successor page, state the reason.
- Remove the page from the Required set of coverage.
- Hard condition of the retirement gate: first run `Tools/check_links.py` to find all incoming links and retarget each one to the successor page; only then may the page be retired.
- For retiring high in-degree pages, the incoming-link retargeting work is converted into a page count at the kernel default of "retargeted-link count ÷ 6" when the selected profile has not overridden it, and counted against the maintenance run budget (rule owner: [[kernel/00 Standards Control/08 Maintenance Run Envelope|00/08]] Maintenance Run Envelope, referenced here); a profile MAY explicitly override this conversion parameter.

## Merge

- Disposition precedence: once duplication is confirmed, the **merge obligation takes precedence** over other dispositions; confirmed duplication MUST NOT be shelved on the grounds of missing authorization.
- The absorbed page is handled through the Retirement tombstone and incoming-link retargeting process, with `superseded_by` pointing to the merged page.
- The merged page MUST absorb the absorbed page's unique content and Sources; silent discarding is prohibited.
- When the absorbed page contains changes whose source cannot be confirmed: absorb all unique content into the canonical page without exception, and record in the tombstone the original location of the source-unclear passages and where they were absorbed — what is preserved is the content, not the page itself.
- Merge and retirement do not require item-by-item governance authorization; only **physical deletion of files** requires governance authorization.

## Downgrade And Subtree Deprecation

- Lowering priority does not go through the retirement process; recording the reason in the Ledger is sufficient.
- When an entire technology branch becomes obsolete, retire it in batches bottom-up in dependency order, executed as one type of maintenance batch.

## Related

- [[kernel/04 Content Depth Standard|Content Depth Standard]]
- [[kernel/05 Terminology Standard|Terminology Standard]]
- [[kernel/09 Wiki Link and Navigation Standard|Wiki Link and Navigation Standard]]
- [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
