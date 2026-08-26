"""Pure machine shape shared by Work Spec producers and consumers.

This module owns no runtime state, validation decision, or write path.  It is
the neutral Tool contract for fields that bind a Queue/Coverage batch to an
immutable Work Spec, so a validator and an Amendment classifier cannot drift
into accepting different spellings of the same pair.
"""


WORK_SPEC_BINDING_FIELDS = frozenset((
    "work_spec_path", "work_spec_sha256",
))
