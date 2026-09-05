"""Bounded CUE evaluation of explicit immutable Profile/contract inputs.

CUE is an implementation dependency, never an adoption authority. The caller
supplies all owner-contract bytes from its admitted snapshot. No candidate
code, imports, policy defaults, or filesystem paths are evaluated as CUE.
Read-only model consumers do not call this module for individual getters.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from Tools.platform.common import kblib


@dataclass(frozen=True)
class CueValidation:
    valid: bool
    diagnostics: tuple


def toolchain_contract():
    """Return the pinned Tool-owned evaluator identity and archive checksums."""
    return json.loads(Path(__file__).with_name("cue-toolchain.json").read_text(encoding="utf-8"))


def _binary_identity(toolchain):
    selected = os.environ.get("CAMBIUM_CUE") or shutil.which("cue")
    if not selected:
        raise ValueError("CUE unavailable; install the pinned toolchain and set CAMBIUM_CUE")
    path = Path(selected).resolve(strict=True)
    stat = path.stat()
    return (str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns,
            stat.st_ctime_ns, toolchain["version"])


@lru_cache(maxsize=8)
def _verified_binary(identity):
    path, *_stat, version = identity
    with tempfile.TemporaryDirectory(prefix="cambium-profile-cue-version-") as directory:
        result = kblib.run_cambium_subprocess(
            [path, "version"], cwd=directory,
            env=_isolated_environment(Path(directory)),
            capture_output=True, text=True, timeout=15)
    if result.returncode or not result.stdout.splitlines() or result.stdout.splitlines()[0] != "cue version " + version:
        raise ValueError("Profile requires CUE %s; evaluator version did not match" % version)
    return path


def _isolated_environment(temporary):
    """Use CUE's own resolution controls, not an approximate import parser.

    A disabled registry alone is insufficient: CUE consults its module cache
    first. Both cache and configuration therefore belong to this invocation.
    Non-CUE variables remain available to the shared subprocess boundary;
    inherited Cambium descriptors are not schema inputs or consumption ACKs.
    """
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("CUE_")}
    environment.update({
        "CUE_REGISTRY": "none",
        "CUE_CACHE_DIR": str(temporary / "cache"),
        "CUE_CONFIG_DIR": str(temporary / "config"),
    })
    return environment


def _json_plain(value):
    if isinstance(value, Mapping):
        return {key: _json_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_plain(item) for item in value]
    return value


@lru_cache(maxsize=64)
def _evaluate(identity, sources, data, draft):
    binary = _verified_binary(identity)
    with tempfile.TemporaryDirectory(prefix="cambium-profile-cue-") as directory:
        temporary = Path(directory)
        # An empty boundary directory stops ancestor-module discovery even
        # when TMPDIR is inside a module. There is deliberately no module.cue,
        # local dependency tree, or registry configuration in this workspace.
        (temporary / "cue.mod").mkdir()
        names = {}
        for relative, content in sources:
            content.decode("utf-8", errors="strict")
            name = "owner_" + hashlib.sha256(relative.encode()).hexdigest()[:24] + ".cue"
            names[name] = relative
            (temporary / name).write_bytes(content)
        (temporary / "candidate.json").write_bytes(data)
        definition = "#ProfileDraft" if draft else "#Profile"
        command = [binary, "vet", "-c", "-d", definition,
                   *sorted(names), "candidate.json"]
        result = kblib.run_cambium_subprocess(
            command, cwd=temporary, env=_isolated_environment(temporary),
            capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return CueValidation(True, ())
        detail = (result.stderr or result.stdout).strip() or "CUE refused the Profile"
        for name, relative in names.items():
            detail = detail.replace(name, relative)
        detail = detail.replace(str(temporary) + os.sep, "")
        return CueValidation(False, tuple(detail.splitlines()))


def validate_profile(document, contract_sources, *, draft=False, toolchain=None):
    """Validate explicit snapshot inputs; failures never use a permissive fallback.

    Cache keys include all document bytes, every owner path/content, validation
    mode, and evaluator identity. This cache contains no current selection.
    """
    if not isinstance(document, Mapping) or not isinstance(contract_sources, Mapping) or not contract_sources:
        return CueValidation(False, ("Profile evaluation needs a document and non-empty owner contracts",))
    try:
        data = json.dumps(_json_plain(document), sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
        sources = tuple((str(path), text.encode("utf-8") if isinstance(text, str) else bytes(text))
                        for path, text in sorted(contract_sources.items()))
        pinned = toolchain if toolchain is not None else toolchain_contract()
        return _evaluate(_binary_identity(pinned), sources, data, bool(draft))
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, subprocess.TimeoutExpired) as exc:
        return CueValidation(False, ("CUE evaluation unavailable or invalid: %s" % exc,))
