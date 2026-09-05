"""Install the pinned Profile evaluator without changing a system runtime.

Reads the same Tool toolchain owner used by Profile evaluation. Downloads are
verified before a single regular executable is published; existing executables
are never overwritten. This is Host setup, not Profile adoption.
"""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import tarfile
import urllib.request
import zipfile

from Tools.platform.common import kblib


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    contract = json.loads((root / "Tools/governance/profile/cue-toolchain.json").read_text())
    system = platform.system().lower()
    architecture = {"aarch64": "arm64", "arm64": "arm64",
                    "x86_64": "amd64", "amd64": "amd64"}.get(platform.machine().lower())
    target = "%s_%s" % (system, architecture)
    expected = contract["archives"].get(target)
    if expected is None:
        parser.error("no pinned CUE archive for %s" % target)
    version = contract["version"]
    suffix = "zip" if system == "windows" else "tar.gz"
    executable = "cue.exe" if system == "windows" else "cue"
    destination = args.destination.absolute()
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / executable
    if output.exists() or output.is_symlink():
        if output.is_symlink() or not output.is_file():
            parser.error("existing target is not a regular executable")
        result = kblib.run_cambium_subprocess([str(output), "version"], capture_output=True, text=True, timeout=15)
        if (result.returncode or not result.stdout.splitlines()
                or result.stdout.splitlines()[0] != "cue version " + version):
            parser.error("existing CUE has a different version; choose a new destination")
        print(output)
        return 0
    archive = "cue_%s_%s.%s" % (version, target, suffix)
    url = "%s/%s/%s" % (contract["release_base"], version, archive)
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(32 * 1024 * 1024 + 1)
    if len(data) > 32 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected:
        parser.error("CUE archive checksum does not match the pinned Tool contract")
    if suffix == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            matches = [name for name in package.namelist() if name == executable]
            if len(matches) != 1:
                parser.error("CUE archive must contain exactly one executable")
            content = package.read(matches[0])
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as package:
            matches = [member for member in package.getmembers()
                       if member.name == executable and member.isfile()]
            if len(matches) != 1:
                parser.error("CUE archive must contain exactly one regular executable")
            content = package.extractfile(matches[0]).read()
    # O_EXCL prevents overwriting another installer or a user-owned target.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o755)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
