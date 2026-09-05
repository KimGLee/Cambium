# Profile Template

This directory supplies an empty candidate for the Kernel-owned Profile interface. The conducting Agent calls the Profile creation capability with a confirmed Profile ID, then writes explicit answers into `profile.toml`. The user does not copy files or edit TOML manually. The template itself is not selectable and does not decide policy.

The only Profile entrypoint is `profile.toml`. Its `slots` object uses the stable slot IDs registered by [K00](../../kernel/K00%20Standards%20Control/profile-interface.yaml); each domain owns its own CUE constraints. Necessary independent policy prose lives under `policies/`, and scan parameters remain under `scan-configs/`. These support files become active only through explicit, validated references from confirmed answers.

The Agent uses [the interview](../interview.yaml) to propose answers and collect confirmation. Missing draft fields remain missing. Creation, validation, a candidate value, and a proposed inactive branch never select a Profile. Only the existing Standards adoption operation can select a version.

For machine validation, use:

```sh
python3 Tools/check_profile.py profiles/<profile-id>
```

A successful check proves the declared machine constraints and reference consistency, not semantic quality, confirmation, or adoption. The [template file list](../template-files.yaml) is Tool-owned copy layout, not an interface owner. It excludes this README.

## Earlier Candidate Suggestions

The earlier template prefilled the following suggestions. They remain orientation material here to preserve their meaning during the format migration; they are not copied into the empty candidate and do not become decisions without confirmation. An Agent may propose relevant suggestions during the interview, then write only the confirmed choice.

- Corpus Planning not applicable: Bounded corpus maintained one note at a time; no corpus-wide capability plan is needed or changed, and no multi-batch construction or migration is planned.
- Structure Registry not applicable: A flat corpus maintained one page at a time; no directory carries a unique responsibility that is built, maintained, or audited independently, so the K01/05 module admission test admits nothing.
- Metadata: use `kernel-defaults` with no instance differences, extensions, relationships, or section-role overrides.
- Priority: no P0/P1 grants; no instance quota registration.
- Vocabulary: no added fields or values; `general: slow` was a proposal for an undivided corpus, requiring explicit confirmation or replacement with its real domains.
- Scope: no exclusions; “Everything else in scope.” as the final priority factor; layer fallbacks require the confirmed layer ID; the Expression Layer predicate was “always false”.
- Conditional scope applicability: this corpus records no production system whose failure, cost, or scaling behaviour would need separate reasoning.; the corpus is small enough to be reviewed in full, so no sample stands in for the whole.; notes are written one at a time as the underlying material appears; there is no bulk build with ordered stages..
- Optional registrations were proposed inactive: expression artifacts, rendering rules, additional language/source rules, extension roles/dimensions, supplemental routes/Gates, extra L-tier triggers, specialized audit requirements, batch review requirements, and escalation triggers. Each remains a choice to confirm, never a missing-field default.
- Metric traceability not applicable: this corpus reports no evaluated metric; every recorded number is an observation governed by Source Policy, with its retrieval date.

The earlier language suggestions, preserved verbatim:

- `secondary_language`: None — monolingual
- `proper_names`: Original spelling everywhere, including headings and tables.
- `external_names`: The official product or project string, unchanged; add a short body-language gloss on first use per page when the name alone is unclear.
- `machine_identifiers`: Identifiers, commands, fields, and file paths appear in backticks and are never re-cased or translated.
- `folders`: Body language, Title Case, spaces; preserve official casing where it differs.
- `pages`: Body language, Title Case, spaces; preserve official casing where it differs.
- `term_notes`: The most common official term, using its conventional casing and punctuation.
- `image_assets`: Lowercase, hyphens; the owning page's slug is the prefix.
- `aliases`: Register the official full form and any materially distinct established synonym; do not create aliases for spelling noise.
- `headings`: Sentence case, no trailing punctuation, no numbering.
- `abbreviations`: Expanded once per page on first use, then the abbreviation alone.
- `display_order`: What it is, where it lives, how to verify it, what breaks it.
- `file_annotations`: None — the file name carries the title only.

The body language and length unit require a confirmed choice. Literal headings, matchers, external names and machine tokens retain the language of the content they identify. Templates and interviews do not impose English-only policy prose.
