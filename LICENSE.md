# Cambium Licensing

Cambium uses scoped licensing: each Cambium-maintained, tracked file in the
official distribution is governed by the license assigned below. The two
licenses are not alternatives for the same material.

## Apache License 2.0 — software and implementation materials

Copyright 2026 KimGLee

The Apache License, Version 2.0 applies to the following Cambium-maintained
files in the official distribution:

- Files tracked under `Tools/**`, including scripts, schemas, and tool
  documentation, except adopter-generated artifacts described below.
- `.gitignore`.
- `NOTICE`.
- Future executable software, runtime adapters, or implementation files only
  when they are explicitly assigned to Apache-2.0.

The complete license text is in
[`LICENSES/Apache-2.0.txt`](LICENSES/Apache-2.0.txt). The Apache-licensed
portion also carries the notice in [`NOTICE`](NOTICE).

## Creative Commons Attribution 4.0 — standards and documentation

Licensed material: Cambium standards and profile materials

Copyright 2026 KimGLee

The Creative Commons Attribution 4.0 International license (CC BY 4.0) applies
to the following Cambium-maintained files in the official distribution:

- Files tracked under `kernel/**`.
- Files tracked under `profiles/**`, except adopter-created profile content
  described below.
- `README.md` and `README.zh-CN.md`.
- `ROADMAP.md`.
- `LICENSE.md` and `ATTRIBUTION.md`.

The complete legal code is in
[`LICENSES/CC-BY-4.0.txt`](LICENSES/CC-BY-4.0.txt). Attribution information
and a reusable attribution form are in
[`ATTRIBUTION.md`](ATTRIBUTION.md).

CC BY 4.0 permits sharing and adaptation, including commercial use, subject to
its terms. In particular, when licensed or adapted material is shared, the
license requires appropriate attribution, retention of the specified notices
where applicable, and an indication of modifications.

## Adopter-Generated Material

File location alone does not transfer ownership or apply a Cambium license to
material created by an adopter. In particular:

- Generated vocabulary files such as `Tools/vocab.yaml`, receipts under
  `Tools/receipts/**`, runtime evidence, and similar instance outputs are not
  licensed by Cambium merely because they are stored under `Tools/`.
- An adopter's original profile answers are not licensed by Cambium merely
  because the profile is stored under `profiles/`. Any portions copied or
  adapted from Cambium's `_template` remain subject to CC BY 4.0; the license
  does not require the adopter to apply CC BY 4.0 to their independent added
  material.

Cambium-originated material reproduced in a generated artifact retains its
applicable license. Adopter-originated values, answers, and evidence do not
become Apache-2.0 or CC BY 4.0 merely because of the artifact's output path.

## License Administration Files

This scope statement, the license copies under `LICENSES/`, `NOTICE`, and
`ATTRIBUTION.md` document the licensing arrangement. The verbatim legal texts
under `LICENSES/` are reproduced as legal instruments and are not assigned a
Cambium project license. None of these files replaces or modifies either
license's legal terms.

Any future Cambium-maintained file outside the scopes listed above must be
explicitly assigned a license here or by an SPDX license identifier before it
is released. No license for otherwise unlisted material is implied by
proximity to licensed material.

## Relicensing Record

Material moved between the two scopes above is recorded here, because the file
paths alone no longer show which license the material was released under
before the move.

- 2026-08-06 — The closed membership registry of profile-overridable execution
  defaults and constitutional constants (the `overridable` and
  `constitutional` blocks) moved from
  `Tools/schemas/execution_defaults.template.yaml`, released under
  Apache-2.0, to `kernel/K00 Standards Control/execution-defaults-base.yaml`,
  released under CC BY 4.0. Both scopes are Cambium-maintained and
  copyright 2026 KimGLee, so the move required no third-party permission; the
  earlier Apache-2.0 release of that material is not withdrawn by it. The
  remaining blocks of the original file stay Apache-2.0 under `Tools/**`.
