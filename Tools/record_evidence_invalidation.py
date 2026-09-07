#!/usr/bin/env python3
"""Stable public command; implementation belongs to execution.evidence."""

import os
import sys

_REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, _REPOSITORY_ROOT)

from Tools.execution.evidence.record_evidence_invalidation import main as _main
from Tools.platform.common.reporting import host_environment_boundary as _host_environment_boundary

IMPLEMENTATION_MODULE = "Tools.execution.evidence.record_evidence_invalidation"


@_host_environment_boundary
def main(argv=None):
    return _main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
