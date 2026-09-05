#!/usr/bin/env python3
"""CI entrypoint for the shared Runtime-carried Profile toolchain installer."""

from pathlib import Path
import sys


REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from Tools.platform.distribution.install_profile_toolchain import main


if __name__ == "__main__":
    raise SystemExit(main())
