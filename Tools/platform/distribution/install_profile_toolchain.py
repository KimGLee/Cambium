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
import zipfile

from Tools.platform.common import kblib
from Tools.platform.common import locked_download
from Tools.platform.common.host_environment import HostEnvironmentUnavailable
from Tools.platform.common import host_toolchain


def install_cue(destination, *, root=None):
    """Shared CLI/Host provider; no Profile parsing or adoption prerequisite."""
    root = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    contract = json.loads((root / "Tools/governance/profile/cue-toolchain.json").read_text())
    system = platform.system().lower()
    architecture = {"aarch64": "arm64", "arm64": "arm64",
                    "x86_64": "amd64", "amd64": "amd64"}.get(platform.machine().lower())
    target = "%s_%s" % (system, architecture)
    expected = contract["archives"].get(target)
    if expected is None:
        raise ValueError("no pinned CUE archive for %s" % target)
    version = contract["version"]
    suffix = "zip" if system == "windows" else "tar.gz"
    executable = "cue.exe" if system == "windows" else "cue"
    destination = Path(destination).absolute()
    if any(path.is_symlink() for path in (destination, *destination.parents)):
        raise ValueError("CUE destination must not traverse symlinks")
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / executable
    if output.exists() or output.is_symlink():
        if output.is_symlink() or not output.is_file():
            raise ValueError("existing target is not a regular executable")
        result = kblib.run_cambium_subprocess([str(output), "version"], capture_output=True, text=True, timeout=15)
        if result.returncode or not host_toolchain.cue_version_matches(result.stdout, version):
            raise ValueError("existing CUE has a different version; choose a new destination")
        return str(output)
    archive = "cue_%s_%s.%s" % (version, target, suffix)
    url = "%s/%s/%s" % (contract["release_base"], version, archive)
    if contract["release_base"] != "https://github.com/cue-lang/cue/releases/download":
        raise ValueError("CUE archive source must be the pinned official release source")
    data = locked_download.download({"url": url}, capability_id="host-environment-preparation-v1",
        limit=32 * 1024 * 1024, redirect_hosts=("release-assets.githubusercontent.com",))
    if len(data) > 32 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("CUE archive checksum does not match the pinned Tool contract")
    if suffix == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            matches = [name for name in package.namelist() if name == executable]
            if len(matches) != 1:
                raise ValueError("CUE archive must contain exactly one executable")
            content = package.read(matches[0])
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as package:
            matches = [member for member in package.getmembers()
                       if member.name == executable and member.isfile()]
            if len(matches) != 1:
                raise ValueError("CUE archive must contain exactly one regular executable")
            content = package.extractfile(matches[0]).read()
    # O_EXCL prevents overwriting another installer or a user-owned target.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o755)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    # Re-enter the same read-only verifier; a successful write is not proof
    # that this platform can execute the prepared evaluator.
    return install_cue(destination, root=root)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        print(install_cue(args.destination))
    except (OSError, ValueError, HostEnvironmentUnavailable) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
