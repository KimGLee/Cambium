#!/usr/bin/env python3
"""Stable component-boundary command and external bytecode boundary."""

import os
import sys
import tempfile


def _external_pycache_prefix():
    """Choose a cache prefix outside the unverified component tree."""
    repository_root = os.path.realpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), os.pardir))
    for raw_root in (tempfile.gettempdir(), "/var/tmp", "/tmp"):
        candidate_root = os.path.realpath(os.path.abspath(raw_root))
        if not os.path.isdir(candidate_root):
            continue
        try:
            if os.path.commonpath(
                    (repository_root, candidate_root)) == repository_root:
                continue
        except ValueError:
            pass
        candidate = os.path.join(
            candidate_root,
            "cambium-adoption-pycache-%s" % os.urandom(16).hex())
        if not os.path.lexists(candidate):
            return candidate
    raise RuntimeError("no repository-external Python cache root is available")


_CAMBIUM_PYCACHE_PREFIX = _external_pycache_prefix()
os.environ["PYTHONPYCACHEPREFIX"] = _CAMBIUM_PYCACHE_PREFIX
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.pycache_prefix = _CAMBIUM_PYCACHE_PREFIX
sys.dont_write_bytecode = True

_REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, _REPOSITORY_ROOT)

from Tools.platform.distribution.check_upstream_components import main as _main

IMPLEMENTATION_MODULE = "Tools.platform.distribution.check_upstream_components"


def main(argv=None):
    return _main(argv)

if __name__ == "__main__":
    raise SystemExit(main())
