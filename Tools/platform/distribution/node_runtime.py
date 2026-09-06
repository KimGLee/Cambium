"""Bounded Node/npm provider. The pinned archive is the only download input.

Extract into a new unselected Host directory, never system locations. The
caller must smoke its requested capabilities before publishing a binding.
"""

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import tarfile
import tempfile
import zipfile

from Tools.platform.common import kblib
from Tools.platform.common import locked_download
from Tools.platform.common.host_environment import HostEnvironmentUnavailable


def node_requirement(root):
    path = Path(root) / "Tools/platform/distribution/node-toolchain.json"
    contract = json.loads(path.read_text(encoding="utf-8"))
    if set(contract) != {"schema_version", "version", "release_base", "checksum_source", "archives"} or \
            type(contract["schema_version"]) is not int or contract["schema_version"] != 1 or \
            not re.fullmatch(r"v\d+\.\d+\.\d+", contract["version"]) or \
            contract["release_base"] != "https://nodejs.org/dist" or \
            contract["checksum_source"] != contract["release_base"] + "/" + contract["version"] + "/SHASUMS256.txt":
        raise ValueError("Invalid managed Node toolchain contract")
    system = {"windows": "win"}.get(platform.system().lower(), platform.system().lower())
    arch = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64"}.get(
        platform.machine().lower(), platform.machine().lower())
    target = system + "-" + arch
    row = contract["archives"].get(target)
    if row is None:
        raise HostEnvironmentUnavailable("No managed Node archive for " + target,
            capability_id="rendering-runtime-preparation-v1", code="platform-unsupported",
            resource=target, remedy="provide-host")
    if set(row) != {"suffix", "sha256"} or row["suffix"] != ("zip" if system == "win" else "tar.gz") or \
            not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
        raise ValueError("Invalid Node archive lock")
    stem = "node-" + contract["version"] + "-" + target
    return {"version": contract["version"], "stem": stem, "target": target, **row,
            "url": contract["release_base"] + "/" + contract["version"] + "/" + stem + "." + row["suffix"]}


def npm_cli(node):
    """Use the npm shipped beside this Node, never an unrelated PATH command."""
    directory = Path(node).resolve().parent
    for candidate in (directory / "npm", directory / "node_modules/npm/bin/npm-cli.js",
                      directory.parent / "lib/node_modules/npm/bin/npm-cli.js"):
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def _extract(data, request, directory):
    """Reject traversal, special entries and escaping links before any extract."""
    records = []
    if request["suffix"] == "zip":
        archive = zipfile.ZipFile(io.BytesIO(data))
        for member in archive.infolist():
            mode = member.external_attr >> 16
            if mode & 0o170000 == 0o120000:
                raise ValueError("Node zip contains an unexpected symlink")
            records.append((member.filename, "dir" if member.is_dir() else "file",
                            member.file_size, mode, member, None))
    else:
        archive = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
        for member in archive.getmembers():
            kind = "dir" if member.isdir() else "file" if member.isfile() else "link" if member.issym() else None
            if kind is None:
                raise ValueError("Node archive contains a special entry")
            records.append((member.name, kind, member.size, member.mode, member, member.linkname))
    with archive:
        seen = set()
        if len(records) > 30000 or sum(row[2] for row in records) > 512 * 1024 * 1024:
            raise ValueError("Node archive exceeds bounded extraction limits")
        targets = []
        for name, kind, size, mode, member, link in records:
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or not relative.parts or \
                    relative.parts[0] != request["stem"] or "\\" in name or ":" in name:
                raise ValueError("Unsafe Node archive path")
            target = directory.joinpath(*relative.parts)
            if target in seen:
                raise ValueError("Repeated Node archive path")
            seen.add(target)
            if kind == "link":
                if not link or "\\" in link or ":" in link or PurePosixPath(link).is_absolute() or \
                        not (target.parent / link).resolve().is_relative_to(directory / request["stem"]):
                    raise ValueError("Escaping Node archive link")
            targets.append((target, kind, mode, member, link))
        links = {target for target, kind, *_ in targets if kind == "link"}
        if any(any(parent in links for parent in target.parents) for target, *_ in targets):
            raise ValueError("Node archive extracts through a symlink")
        for target, kind, mode, member, link in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            if kind == "dir":
                target.mkdir(exist_ok=True)
            elif kind == "file":
                content = archive.read(member) if request["suffix"] == "zip" else archive.extractfile(member).read()
                with target.open("xb") as output:
                    output.write(content)
                target.chmod(0o755 if mode & 0o111 else 0o644)
        for target, kind, _mode, _member, link in targets:
            if kind == "link":
                target.symlink_to(link)




def prepare_node(root, cache, *, created=None):
    """Download a pinned archive into a new candidate; caller owns selection."""
    request = node_requirement(root)
    cache = Path(cache).absolute()
    if cache.resolve().is_relative_to(Path(root).resolve()) or any(p.is_symlink() for p in (cache, *cache.parents)):
        raise ValueError("Managed Node cache must be a non-symlink Host location outside the repository")
    data = locked_download.download(request, capability_id="rendering-runtime-preparation-v1",
                                    limit=128 * 1024 * 1024)
    if len(data) > 128 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != request["sha256"]:
        raise ValueError("Node archive differs from its pinned checksum")
    cache.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix="node-", dir=str(cache)))
    if created is not None:
        created.append(str(destination))
    _extract(data, request, destination)
    installed = destination / request["stem"]
    node = installed / ("node.exe" if request["target"].startswith("win-") else "bin/node")
    npm = npm_cli(node)
    if not node.is_file() or not os.access(node, os.X_OK) or not npm:
        raise ValueError("Managed Node/npm archive is incomplete")
    result = kblib.run_cambium_subprocess([str(node), "--version"], capture_output=True,
                                         text=True, timeout=30, check=False)
    if result.returncode or result.stdout.strip() != request["version"]:
        raise ValueError("Installed Node does not match the pinned release")
    return str(node.resolve())


__all__ = ["node_requirement", "npm_cli", "prepare_node"]
