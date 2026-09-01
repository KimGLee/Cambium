#!/usr/bin/env python3
"""Stable public command; implementation lives at :mod:`Tools.platform.agent_interface.compile_cli_contract`."""

import os
import sys

_REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, _REPOSITORY_ROOT)

from Tools.platform.agent_interface.compile_cli_contract import main as _main

IMPLEMENTATION_MODULE = "Tools.platform.agent_interface.compile_cli_contract"

def main(argv=None):
    return _main(argv)

if __name__ == "__main__":
    raise SystemExit(main())
