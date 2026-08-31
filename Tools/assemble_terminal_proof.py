#!/usr/bin/env python3
"""Stable public command for the Terminal Proof producer."""

import os
import sys

_REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, _REPOSITORY_ROOT)

from Tools.execution.audit.assemble_terminal_proof import main as _main

IMPLEMENTATION_MODULE = "Tools.execution.audit.assemble_terminal_proof"


def main(argv=None):
    return _main(argv)


if __name__ == "__main__":
    sys.exit(main())
