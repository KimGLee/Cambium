"""Prepare locked rendering dependencies in Host user space, never in a corpus.

Discovery is read-only by default. Explicit --apply permits an npm ci with
scripts disabled in a fresh cache directory and publishes checked Host bindings.
It does not install a system Node/browser, approve policy, or write a Receipt.
"""

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlparse

from Tools.knowledge.rendering import static_render_runtime as runtime
from Tools.platform.common import kblib


CAPABILITY_ID = "rendering-runtime-preparation-v1"


def _installation_inputs(requirement):
    """Only the shipped, integrity-bound HTTPS npm tarballs may be installed."""
    for path, record in requirement["packages"].items():
        if path == "":
            continue
        relative = PurePosixPath(path)
        url = urlparse(record.get("resolved", ""))
        if (relative.is_absolute() or ".." in relative.parts or
                not path.startswith("node_modules/") or record.get("link") or
                url.scheme != "https" or url.hostname != "registry.npmjs.org" or
                url.username or url.password or url.query or url.fragment or
                not re.fullmatch(r"sha512-[A-Za-z0-9+/]+={0,2}", record.get("integrity", ""))):
            raise runtime.StaticRenderRuntimeError("Unsafe or unlocked renderer dependency: " + path)


def _publish_bindings(root, target, bindings):
    requirement = runtime.runtime_requirements(root)
    document = {key: requirement[key] for key in (
        "capability_id", "package_sha256", "package_lock_sha256")}
    document.update({"schema_version": 1, "bindings": bindings})
    before = None
    if target.exists() or target.is_symlink():
        before = target.read_bytes()
        existing = runtime.read_runtime_bindings(root, target, check_executables=False)
        if existing == bindings:
            return
    descriptor, temporary = tempfile.mkstemp(prefix=".bindings-", dir=str(target.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if before is None:
            # First publication never clobbers an existing binding.
            os.link(temporary, target)
        else:
            # Explicit preparation may add a now-available browser or refresh
            # discovered Host paths. Only this checked, owner-shaped projection
            # is replaced; dependency installations and user files are untouched.
            if target.is_symlink() or target.read_bytes() != before:
                raise runtime.StaticRenderRuntimeError("Host bindings changed during preparation")
            os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    runtime.read_runtime_bindings(root, target)


def prepare_runtime(root, *, apply=False, require_browser=False):
    """Discover, optionally prepare, smoke-test, and publish local bindings."""
    root = Path(root).resolve()
    target = runtime.default_runtime_bindings_path(root)
    if target.resolve().is_relative_to(root) or target.parent.is_symlink():
        raise runtime.StaticRenderRuntimeError("Rendering cache must be Host-owned outside the repository")
    probe = runtime.probe_runtime(root, require_browser=require_browser)
    result = dict(probe, capability_id=CAPABILITY_ID, applied=False,
                  bindings_path=str(target), smoke=None)
    if not apply or probe["result"] == "invalid":
        return result
    bindings = dict(probe["bindings"])
    if not bindings.get("CAMBIUM_RENDER_NODE") or (
            require_browser and not bindings.get("CAMBIUM_RENDER_BROWSER")):
        result["findings"].append("Agent must provision the missing supported Node/browser under Host authorization")
        return result
    requirement = runtime.runtime_requirements(root)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not bindings.get("CAMBIUM_RENDER_NODE_MODULES"):
        _installation_inputs(requirement)
        npm = shutil.which("npm")
        if not npm:
            result["findings"].append("npm is unavailable; Agent must provision a supported Host Node/npm installation")
            return result
        # A distinct directory is never reused/overwritten after a failed install.
        install = Path(tempfile.mkdtemp(prefix="npm-", dir=str(target.parent)))
        for name, source in (("package.json", requirement["manifest"]),
                             ("package-lock.json", requirement["lock"])):
            shutil.copyfile(source, install / name)
        environment = dict(os.environ)
        environment.pop("NODE_OPTIONS", None)
        environment.pop("NODE_PATH", None)
        for key in list(environment):
            if key.lower().startswith("npm_config_"):
                environment.pop(key)
        environment["PATH"] = str(Path(bindings["CAMBIUM_RENDER_NODE"]).parent) + os.pathsep + environment.get("PATH", "")
        for key, name in (("NPM_CONFIG_USERCONFIG", ".npm-user-config"),
                          ("NPM_CONFIG_GLOBALCONFIG", ".npm-global-config")):
            isolated_config = install / name
            isolated_config.touch(exist_ok=False)
            environment[key] = str(isolated_config)
        environment["NPM_CONFIG_CACHE"] = str(install / ".npm-cache")
        try:
            completed = kblib.run_cambium_subprocess([
                str(Path(npm).resolve()), "ci", "--ignore-scripts", "--no-audit", "--no-fund",
                "--registry=https://registry.npmjs.org", "--strict-ssl=true"],
                cwd=str(install), env=environment, text=True, capture_output=True,
                timeout=300, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise runtime.StaticRenderRuntimeError("npm preparation failed; unselected cache retained at %s: %s" % (install, exc)) from exc
        if completed.returncode:
            raise runtime.StaticRenderRuntimeError("npm preparation failed; unselected cache retained at %s: %s" %
                                                  (install, completed.stderr[-2000:]))
        bindings["CAMBIUM_RENDER_NODE_MODULES"] = str(install / "node_modules")
    # An exit code is insufficient: resolve actual imports and, when needed,
    # launch the real browser to render synthetic diagram/math/table constructs.
    result["smoke"] = runtime.verify_runtime_bindings(root, bindings, require_browser=require_browser)
    _publish_bindings(root, target, bindings)
    verified = runtime.read_runtime_bindings(root, target)
    result.update(result="ready", applied=True, findings=[], bindings=verified)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--apply", action="store_true", help="Explicitly authorize bounded Host-cache installation")
    parser.add_argument("--require-browser", action="store_true", help="Also verify actual browser rendering")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = prepare_runtime(args.root, apply=args.apply, require_browser=args.require_browser)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {"result": "invalid", "capability_id": CAPABILITY_ID,
                  "applied": False, "findings": [str(exc)], "bindings": {}}
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else
          result["result"] + ": " + "; ".join(result["findings"]))
    return 0 if result["result"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
