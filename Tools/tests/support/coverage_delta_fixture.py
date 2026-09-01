"""Single fixture owner for current pre-merge Coverage Delta bytes.

Tests call this helper when they need a candidate Delta.  The helper exposes
no status parameter: a pre-merge Delta is always ``drafted``.  Reviewed
Coverage rows and reviewed page projections belong to post-close fixtures and
must be built by the Queue close writer instead of by this module.
"""

from pathlib import Path

import Tools.platform.common.kblib as kblib


FIXTURE_OWNER = (
    "Tools.tests.support.coverage_delta_fixture.premerge_delta_document"
)


def premerge_delta_document(
        batch_id, object_path, gate_receipts, *, generated_at,
        open_gaps_added=(), open_gaps_closed=(), next_batch_updates=(),
        watermark_advance=None):
    """Return the one supported fixture shape for a pre-merge Delta."""
    return {
        "batch": batch_id,
        "generated_at": generated_at,
        "pages": [{
            "path": object_path,
            "authoring_status": "drafted",
            "gate_receipts": list(gate_receipts),
        }],
        "open_gaps_added": list(open_gaps_added),
        "open_gaps_closed": list(open_gaps_closed),
        "next_batch_updates": list(next_batch_updates),
        "watermark_advance": watermark_advance,
    }


def write_premerge_delta(
        root, relative, batch_id, object_path, gate_receipts, *, generated_at,
        open_gaps_added=(), open_gaps_closed=(), next_batch_updates=(),
        watermark_advance=None):
    """Write canonical pre-merge Delta fixture bytes and return the path."""
    document = premerge_delta_document(
        batch_id, object_path, gate_receipts, generated_at=generated_at,
        open_gaps_added=open_gaps_added,
        open_gaps_closed=open_gaps_closed,
        next_batch_updates=next_batch_updates,
        watermark_advance=watermark_advance,
    )
    target = Path(root) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(kblib.canonical_yaml(document), encoding="utf-8")
    return relative
