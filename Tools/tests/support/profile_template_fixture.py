"""Single test fixture for completing the canonical Profile template."""

from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[3]
TEMPLATE = REPOSITORY / "profiles" / "_template"
ORIENTATION = ("README.md",)
SENTINEL = "TODO(profile)"
PROFILE_ID = "fill-e2e"

# Every old value is an exact anchor in the canonical template.  Consumers
# replace the fixture identity when a scenario needs a different Profile ID.
FILL = [
    ("profile.md", "`TODO(profile)`", "`fill-e2e`"),
    ("scope-and-architecture.md", "| TODO(profile) | TODO(profile) |\n\n## Content", "| Keep one maintainer's home-lab service notes findable, current, and safe to act on a year later. | The single maintainer who runs the lab. |\n\n## Content"),
    ("scope-and-architecture.md", "| 1 | TODO(profile) |", "| 1 | The note is needed while something is broken. |"),
    ("scope-and-architecture.md", "| TODO(profile) | TODO(profile) | TODO(profile) |\n\n## Knowledge Spine", "| L-MAIN | Notes | Own every canonical note, including dated scratch entries under `Notes/Daily Log`. |\n\n## Knowledge Spine"),
    ("scope-and-architecture.md", "| TODO(profile) | TODO(profile) |\n\n## Placement", "| One page per service or recurring procedure; each page names what it depends on. | The `depends_on` sentence in the page's opening paragraph. |\n\n## Placement"),
    ("scope-and-architecture.md", "| `Shared Foundation Layer` | Layer ID | TODO(profile) |", "| `Shared Foundation Layer` | Layer ID | L-MAIN |"),
    ("scope-and-architecture.md", "| `Production Systems Layer` | Layer ID | None — fallback TODO(profile) |", "| `Production Systems Layer` | Layer ID | None — fallback L-MAIN |"),
    ("scope-and-architecture.md", "| `Cross-domain Concepts Layer` | Layer ID | None — fallback TODO(profile) |", "| `Cross-domain Concepts Layer` | Layer ID | None — fallback L-MAIN |"),
    ("scope-and-architecture.md", "| `Case Study Layer` | Layer ID | None — fallback TODO(profile) |", "| `Case Study Layer` | Layer ID | None — fallback L-MAIN |"),
    ("scope-and-architecture.md", "| `Source Note Layer` | Layer ID | None — fallback TODO(profile) |", "| `Source Note Layer` | Layer ID | None — fallback L-MAIN |"),
    ("scope-and-architecture.md", "| `Research Synthesis Layer` | Layer ID | None — fallback TODO(profile) |", "| `Research Synthesis Layer` | Layer ID | None — fallback L-MAIN |"),
    ("scope-and-architecture.md", "| 1 | TODO(profile) | TODO(profile) |", "| 1 | The page is a dated entry whose title starts with an ISO date. | L-MAIN |"),
    ("scope-and-architecture.md", "| Last | Otherwise | TODO(profile) |", "| Last | Otherwise | L-MAIN |"),
    ("scope-and-architecture.md", "| TODO(profile) | TODO(profile) | TODO(profile) |\n\n## Foundation", "| Service names used in more than one note. | L-MAIN | Included when the name is ambiguous across vendors; excluded when upstream documentation is the only reader-facing form. |\n\n## Foundation"),
    ("scope-and-architecture.md", "| TODO(profile) | TODO(profile) |\n\n## Production", "| A page describing a service the maintainer must restore. | The page names the service, its current version, where its configuration backup lives, and the one command used to verify it is working. |\n\n## Production"),
    ("language-contract.md", "| Body language (language name or tag) | TODO(profile) |", "| Body language (language name or tag) | English (`en`). |"),
    ("source-policy.md", "| 1 | TODO(profile) | TODO(profile) | TODO(profile) |", "| 1 | `maintainer-observation` — what the maintainer observed on the running service itself. | The configuration and version actually running in the lab. | Retrieval date recorded in the note's opening paragraph. |"),
    ("source-policy.md", "| TODO(profile) | TODO(profile) | TODO(profile) | TODO(profile) |", "| A claim about what is currently running. | `maintainer-observation` | Log in to the service and read the status screen named in the note. | 180 days. |"),
    ("source-policy.md", "| TODO(profile) | TODO(profile) |", "| A service is upgraded or replaced. | Every claim on that service's page about versions, defaults, or verification screens. |"),
    ("registries/audit-dimensions.md", "| TODO(profile) | `content_and_depth`", "| `fill-e2e-foundation-depth` | `content_and_depth`"),
    ("registries/audit-dimensions.md", "| `emits` | TODO(profile) |\n| TODO(profile) | `coverage_and_integration`", "| `emits` | `profiles/fill-e2e/scope-and-architecture.md#Foundation Depth Requirements` |\n| `fill-e2e-residual-disposition` | `coverage_and_integration`"),
    ("registries/audit-dimensions.md", "| `emits` | TODO(profile) |\n\n## Residual Disposition", "| `emits` | `profiles/fill-e2e/registries/audit-dimensions.md#Residual Disposition` |\n\n## Residual Disposition"),
    ("registries/audit-dimensions.md", "## Residual Disposition\n\nTODO(profile)", "## Residual Disposition\n\nThe registered scan reports canonical notes that still carry dated-scratch structure outside `Notes/Daily Log`. Each candidate is resolved one of two ways, recorded on the candidate page: the scratch material is moved into the dated entry that owns it, or the page states why that structure is the canonical form for this note."),
    ("registries/registered-scans.md", "| TODO(profile) | `K12/09 item 6 — residual-content scan` | TODO(profile) | `residual-content-scan-v1` | `scan-configs/residual-scan.yaml` | TODO(profile) | TODO(profile) |", "| `fill-e2e-scratch-residuals` | `K12/09 item 6 — residual-content scan` | Run from the vault root; the profile-owned configuration accepts `Notes/Daily Log` as the only root where dated-scratch structure belongs. | `residual-content-scan-v1` | `profiles/fill-e2e/scan-configs/residual-scan.yaml` | A Markdown file outside `Notes/Daily Log` is a candidate when it declares `type: daily-log`, carries a `Daily Log Entry` heading, or carries at least two distinct dated-scratch sorting headings. Candidate-only; adjudication belongs to `fill-e2e-residual-disposition`. | `fill-e2e-residual-disposition` |"),
    ("registries/roles.md", "| `proposer` | TODO(profile) |", "| `proposer` | `fill-e2e-agent` |"),
    ("registries/roles.md", "| `gatekeeper` | TODO(profile) |", "| `gatekeeper` | `fill-e2e-maintainer` |"),
    ("registries/roles.md", "| `executor` | TODO(profile) |", "| `executor` | `fill-e2e-agent` |"),
    ("registries/roles.md", "| `stopper` | TODO(profile) |", "| `stopper` | `fill-e2e-maintainer` |"),
    ("registries/roles.md", "| `knowledge-host` | TODO(profile) |", "| `knowledge-host` | Markdown repository tree |"),
    ("registries/roles.md", "| `knowledge-host UI` | TODO(profile) |", "| `knowledge-host UI` | None — headless |"),
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


def fill_profile(profile, profile_id=PROFILE_ID):
    """Fill a copied canonical template with this fixture's confirmed values."""
    profile = Path(profile)
    for relative, old, new in FILL:
        path = profile / relative
        text = path.read_text(encoding="utf-8")
        expected = old.replace(PROFILE_ID, profile_id)
        replacement = new.replace(PROFILE_ID, profile_id)
        if expected not in text:
            raise AssertionError((relative, expected))
        path.write_text(text.replace(expected, replacement, 1), encoding="utf-8")
    (profile / "scan-configs" / "residual-scan.yaml").write_text(
        SCAN_CONFIG.replace(PROFILE_ID, profile_id), encoding="utf-8"
    )
    return profile


def fill_scaffolded_profile(profile, profile_id=PROFILE_ID):
    """Fill the same answers after the scaffolder's mechanical rewrites.

    The scaffolder deterministically binds the Profile ID and two self paths
    before the interview answers are supplied.  Keep that four-anchor bridge
    in the fixture owner instead of teaching an E2E test a second answer set.
    """
    profile = Path(profile)
    mechanically_bound = []
    for relative, old, new in FILL:
        path = profile / relative
        text = path.read_text(encoding="utf-8")
        expected = old.replace(PROFILE_ID, profile_id)
        replacement = new.replace(PROFILE_ID, profile_id)
        if expected not in text:
            mechanically_bound.append((relative, old))
            continue
        path.write_text(
            text.replace(expected, replacement, 1), encoding="utf-8")

    expected_bound = {
        ("profile.md", "`TODO(profile)`"),
        ("registries/audit-dimensions.md",
         "| `emits` | TODO(profile) |\n| TODO(profile) | "
         "`coverage_and_integration`"),
        ("registries/audit-dimensions.md",
         "| `emits` | TODO(profile) |\n\n## Residual Disposition"),
        ("registries/registered-scans.md",
         "| TODO(profile) | `K12/09 item 6 — residual-content scan` | "
         "TODO(profile) | `residual-content-scan-v1` | "
         "`scan-configs/residual-scan.yaml` | TODO(profile) | "
         "TODO(profile) |"),
    }
    if set(mechanically_bound) != expected_bound:
        raise AssertionError(
            "scaffolder/template ownership drifted: %r" %
            mechanically_bound)

    config_reference = (
        "`profiles/%s/scan-configs/residual-scan.yaml`" % profile_id)
    post_scaffold = (
        (
            "registries/audit-dimensions.md",
            "| TODO(profile) | `coverage_and_integration`",
            "| `%s-residual-disposition` | `coverage_and_integration`" %
            profile_id,
        ),
        (
            "registries/registered-scans.md",
            "| TODO(profile) | `K12/09 item 6 — residual-content scan` "
            "| TODO(profile) | `residual-content-scan-v1` | %s "
            "| TODO(profile) | TODO(profile) |" % config_reference,
            "| `{pid}-scratch-residuals` | `K12/09 item 6 — "
            "residual-content scan` | Run from the vault root; the "
            "profile-owned configuration accepts `Notes/Daily Log` as the "
            "only root where dated-scratch structure belongs. | "
            "`residual-content-scan-v1` | {config_reference} | A Markdown "
            "file outside `Notes/Daily Log` is a candidate when it declares "
            "`type: daily-log`, carries a `Daily Log Entry` heading, or "
            "carries at least two distinct dated-scratch sorting headings. "
            "Candidate-only; adjudication belongs to "
            "`{pid}-residual-disposition`. | "
            "`{pid}-residual-disposition` |".format(
                pid=profile_id, config_reference=config_reference),
        ),
    )
    for relative, old, new in post_scaffold:
        path = profile / relative
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise AssertionError(
                "post-scaffold anchor drifted in %s" % relative)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    (profile / "scan-configs" / "residual-scan.yaml").write_text(
        SCAN_CONFIG.replace(PROFILE_ID, profile_id), encoding="utf-8")
    return profile


__all__ = [
    "FILL",
    "ORIENTATION",
    "PROFILE_ID",
    "SCAN_CONFIG",
    "SENTINEL",
    "TEMPLATE",
    "fill_profile",
    "fill_scaffolded_profile",
]
