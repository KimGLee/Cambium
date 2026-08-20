"""End-to-end regression for `profiles/_template`.

The template ships every legal exit state pre-closed and every operational
default pre-filled, leaving open exactly the decisions no template can make. Two properties keep that promise honest, and this module pins both:

1. Shape: validating the unfilled template fails on nothing but the open
   placeholder markers and the unfilled profile identity — zero structural or
   declaration errors, and no failure inside an orientation file
   (README.md / interview.yaml / answer-patterns.md).
2. Fill: instantiating the open decisions with a synthetic small corpus and
   deleting the orientation files yields a profile `check_profile.py` accepts
   completely.

Because the fill below quotes the template's own text, a template wording
change that breaks the interview surface fails here loudly instead of
reaching an adopter. This is a regression test, not a gate: it records no
receipt, claims no Gate ID, and judges no answer quality.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
TEMPLATE = REPOSITORY / "profiles" / "_template"
CHECK_PROFILE = REPOSITORY / "Tools" / "check_profile.py"
ORIENTATION = ("README.md",)
SHARED = ("interview.yaml", "answer-patterns.md")  # profiles/-level, template-independent
SENTINEL = "TODO(profile)"

PROFILE_ID = "fill-e2e"

# (file, old, new) — every `old` must exist verbatim in the template.
FILL = [
    ("profile.md", "`TODO(profile)`", "`fill-e2e`"),
    ("scope-and-architecture.md",
     "| TODO(profile) | TODO(profile) |\n\n## Content",
     "| Keep one maintainer's home-lab service notes findable, current, and "
     "safe to act on a year later. | The single maintainer who runs the lab. "
     "|\n\n## Content"),
    ("scope-and-architecture.md",
     "| 1 | TODO(profile) |",
     "| 1 | The note is needed while something is broken. |"),
    ("scope-and-architecture.md",
     "| TODO(profile) | TODO(profile) | TODO(profile) |\n\n## Knowledge Spine",
     "| L-MAIN | Notes | Own every canonical note, including dated scratch "
     "entries under `Notes/Daily Log`. |\n\n## Knowledge Spine"),
    ("scope-and-architecture.md",
     "| TODO(profile) | TODO(profile) |\n\n## Placement",
     "| One page per service or recurring procedure; each page names what it "
     "depends on. | The `depends_on` sentence in the page's opening "
     "paragraph. |\n\n## Placement"),
    ("scope-and-architecture.md",
     "| `Shared Foundation Layer` | Layer ID | TODO(profile) |",
     "| `Shared Foundation Layer` | Layer ID | L-MAIN |"),
    ("scope-and-architecture.md",
     "| `Production Systems Layer` | Layer ID | None — fallback TODO(profile) |",
     "| `Production Systems Layer` | Layer ID | None — fallback L-MAIN |"),
    ("scope-and-architecture.md",
     "| `Cross-domain Concepts Layer` | Layer ID | None — fallback TODO(profile) |",
     "| `Cross-domain Concepts Layer` | Layer ID | None — fallback L-MAIN |"),
    ("scope-and-architecture.md",
     "| `Case Study Layer` | Layer ID | None — fallback TODO(profile) |",
     "| `Case Study Layer` | Layer ID | None — fallback L-MAIN |"),
    ("scope-and-architecture.md",
     "| `Source Note Layer` | Layer ID | None — fallback TODO(profile) |",
     "| `Source Note Layer` | Layer ID | None — fallback L-MAIN |"),
    ("scope-and-architecture.md",
     "| `Research Synthesis Layer` | Layer ID | None — fallback TODO(profile) |",
     "| `Research Synthesis Layer` | Layer ID | None — fallback L-MAIN |"),
    ("scope-and-architecture.md",
     "| 1 | TODO(profile) | TODO(profile) |",
     "| 1 | The page is a dated entry whose title starts with an ISO date. "
     "| L-MAIN |"),
    ("scope-and-architecture.md",
     "| Last | Otherwise | TODO(profile) |",
     "| Last | Otherwise | L-MAIN |"),
    ("scope-and-architecture.md",
     "| TODO(profile) | TODO(profile) | TODO(profile) |\n\n## Foundation",
     "| Service names used in more than one note. | L-MAIN | Included when "
     "the name is ambiguous across vendors; excluded when upstream "
     "documentation is the only reader-facing form. |\n\n## Foundation"),
    ("scope-and-architecture.md",
     "| TODO(profile) | TODO(profile) |\n\n## Production",
     "| A page describing a service the maintainer must restore. | The page "
     "names the service, its current version, where its configuration backup "
     "lives, and the one command used to verify it is working. "
     "|\n\n## Production"),
    ("language-contract.md",
     "| Body language (language name or tag) | TODO(profile) |",
     "| Body language (language name or tag) | English (`en`). |"),
    ("source-policy.md",
     "| 1 | TODO(profile) | TODO(profile) | TODO(profile) |",
     "| 1 | `maintainer-observation` — what the maintainer observed on the "
     "running service itself. | The configuration and version actually "
     "running in the lab. | Retrieval date recorded in the note's opening "
     "paragraph. |"),
    ("source-policy.md",
     "| TODO(profile) | TODO(profile) | TODO(profile) | TODO(profile) |",
     "| A claim about what is currently running. | `maintainer-observation` "
     "| Log in to the service and read the status screen named in the note. "
     "| 180 days. |"),
    ("source-policy.md",
     "| TODO(profile) | TODO(profile) |",
     "| A service is upgraded or replaced. | Every claim on that service's "
     "page about versions, defaults, or verification screens. |"),
    ("registries/audit-dimensions.md",
     "| TODO(profile) | `content_and_depth`",
     "| `fill-e2e-foundation-depth` | `content_and_depth`"),
    ("registries/audit-dimensions.md",
     "| `emits` | TODO(profile) |\n| TODO(profile) | `coverage_and_integration`",
     "| `emits` | `profiles/fill-e2e/scope-and-architecture.md#Foundation "
     "Depth Requirements` |\n| `fill-e2e-residual-disposition` "
     "| `coverage_and_integration`"),
    ("registries/audit-dimensions.md",
     "| `emits` | TODO(profile) |\n\n## Residual Disposition",
     "| `emits` | `profiles/fill-e2e/registries/audit-dimensions.md#Residual "
     "Disposition` |\n\n## Residual Disposition"),
    ("registries/audit-dimensions.md",
     "TODO(profile) — state, in two or three sentences, what the registered "
     "scan's\ncandidates mean for this corpus and the two or three legal ways "
     "a candidate is\nresolved (moved into its accepted root, or the page "
     "states why this structure\nis canonical here).",
     "The registered scan reports canonical notes that still carry "
     "dated-scratch structure outside `Notes/Daily Log`. Each candidate is "
     "resolved one of two ways, recorded on the candidate page: the scratch "
     "material is moved into the dated entry that owns it, or the page states "
     "why that structure is the canonical form for this note."),
    ("registries/registered-scans.md",
     "| TODO(profile) | `K12/09 item 6 — residual-content scan` "
     "| TODO(profile) | TODO(profile) | TODO(profile) | TODO(profile) |",
     "| `fill-e2e-scratch-residuals` | `K12/09 item 6 — residual-content "
     "scan` | Run from the vault root, passed as `.`; the profile-owned "
     "configuration accepts `Notes/Daily Log` as the only root where "
     "dated-scratch structure belongs. | `python3 "
     "Tools/check_residual_content.py . --scan-id fill-e2e-scratch-residuals "
     "--config profiles/fill-e2e/scan-configs/residual-scan.yaml "
     "--time-limit 55` | A Markdown file outside `Notes/Daily Log` is a "
     "candidate when it declares `type: daily-log`, carries a `Daily Log "
     "Entry` heading, or carries at least two distinct dated-scratch sorting "
     "headings. Candidate-only; adjudication belongs to "
     "`fill-e2e-residual-disposition`. | `fill-e2e-residual-disposition` |"),
]

SCAN_CONFIG = """# Machine matching parameters for the fill-e2e scratch-residual scan.

residual_scan_config_version: 1

allowed_roots:
  - Notes/Daily Log

excluded_roots: []

frontmatter_match:
  field: type
  values:
    - daily-log

heading_match:
  any:
    - Daily Log Entry
  combination:
    - Scratch
    - To Sort
    - Loose Ends
  minimum_distinct: 2

mandated_headings:
  - Daily Log Entry
  - Scratch
  - To Sort
  - Loose Ends
"""


def run_check(profile_relpath, cwd):
    return subprocess.run(
        [sys.executable, str(CHECK_PROFILE), profile_relpath,
         "--root", str(cwd)],
        cwd=str(cwd), text=True, capture_output=True, check=False)


class TemplateShape(unittest.TestCase):
    def test_template_exists_with_orientation_files(self):
        self.assertTrue((TEMPLATE / "profile.md").is_file())
        for name in ORIENTATION:
            self.assertTrue((TEMPLATE / name).is_file(), name)
        for name in SHARED:
            self.assertTrue(
                (REPOSITORY / "profiles" / name).is_file(),
                "shared adoption file missing at profiles/ level: %s" % name)
            self.assertFalse(
                (TEMPLATE / name).is_file(),
                "%s must live at profiles/ level, not inside the template"
                % name)

    def test_unfilled_failures_are_exactly_the_open_decisions(self):
        result = run_check("profiles/_template", REPOSITORY)
        self.assertNotEqual(0, result.returncode)
        fail_lines = [l for l in result.stdout.splitlines()
                      if l.strip().startswith("[FAIL")]
        self.assertTrue(fail_lines, result.stdout)
        for line in fail_lines:
            self.assertTrue(
                "unfilled-placeholder" in line or "profile-id-invalid" in line,
                "unexpected structural failure in the shipped template: %s"
                % line)
            for name in ORIENTATION:
                self.assertNotIn(
                    "_template/%s" % name, line,
                    "orientation file must carry no sentinel: %s" % line)


class TemplateFillEndToEnd(unittest.TestCase):
    def test_filled_copy_passes_check_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            # Reuse the producer-derived closed Profile-load fixture instead
            # of maintaining a second, inevitably stale interface subset.
            from Tools.tests import test_profile_onboarding_status as fixture
            fixture.copy_profile_load_fixture(root)
            profile = root / "profiles" / PROFILE_ID
            shutil.copytree(TEMPLATE, profile)
            for name in ORIENTATION:
                (profile / name).unlink()
            for rel, old, new in FILL:
                path = profile / rel
                text = path.read_text(encoding="utf-8")
                self.assertIn(
                    old, text,
                    "template wording drifted; update FILL for %s" % rel)
                path.write_text(text.replace(old, new, 1), encoding="utf-8")
            (profile / "scan-configs" / "residual-scan.yaml").write_text(
                SCAN_CONFIG, encoding="utf-8")
            result = run_check("profiles/%s" % PROFILE_ID, root)
            self.assertEqual(
                0, result.returncode, result.stdout + result.stderr)
            self.assertIn("sentinel_hits(fail)=0", result.stdout)
            self.assertNotIn(SENTINEL, result.stdout)


if __name__ == "__main__":
    unittest.main()
