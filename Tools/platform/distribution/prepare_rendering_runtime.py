"""Prepare locked rendering dependencies in Host user space, never in a corpus.

Discovery is read-only by default. Explicit --apply permits an npm ci with
scripts disabled in a fresh cache directory and publishes checked Host bindings.
Requested constructs select Playwright's pinned Chromium only when needed in
the Host cache. It never selects the user's daily browser implicitly, installs a
system runtime, approves policy, or writes a Receipt.
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
from Tools.platform.common.host_environment import HostEnvironmentUnavailable, preparation_failure
from Tools.platform.distribution import node_runtime


CAPABILITY_ID = "rendering-runtime-preparation-v1"
_UNOBSERVED = object()


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


def _publish_bindings(root, target, bindings, *, expected_before=_UNOBSERVED, report=None):
    requirement = runtime.runtime_requirements(root)
    document = {key: requirement[key] for key in (
        "capability_id", "package_sha256", "package_lock_sha256")}
    document.update({"schema_version": 1, "bindings": bindings})
    before = None
    if target.exists() or target.is_symlink():
        before = target.read_bytes()
        existing = runtime.binding_document(root, target)
        if expected_before is not _UNOBSERVED and before != expected_before:
            raise runtime.StaticRenderRuntimeError("Host bindings changed during preparation")
        if existing == bindings:
            runtime.read_runtime_bindings(root, target)
            if report is not None:
                report.update(published=False, read_back=True)
            return
    elif expected_before is not _UNOBSERVED and expected_before is not None:
        raise runtime.StaticRenderRuntimeError("Host bindings disappeared during preparation")
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
        if report is not None:
            report["published"] = True
    finally:
        Path(temporary).unlink(missing_ok=True)
    runtime.read_runtime_bindings(root, target)
    if report is not None:
        report["read_back"] = True


def _install_browser(root, cache, bindings, *, created=None):
    """Let the locked Playwright package own platform and browser revision."""
    package = Path(bindings["CAMBIUM_RENDER_NODE_MODULES"]) / "playwright-core"
    destination = Path(tempfile.mkdtemp(prefix="chromium-", dir=str(cache)))
    if created is not None:
        created.append(str(destination))
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("PLAYWRIGHT_") and key not in {"NODE_OPTIONS", "NODE_PATH"}}
    environment["PLAYWRIGHT_BROWSERS_PATH"] = str(destination)
    command = [bindings["CAMBIUM_RENDER_NODE"], str(package / "cli.js"),
               "install", "chromium", "--no-shell"]
    completed = kblib.run_cambium_subprocess(command, env=environment,
        text=True, capture_output=True, timeout=600, check=False)
    if completed.returncode:
        raise runtime.StaticRenderRuntimeError("Managed Chromium installation failed; unselected cache retained at %s: %s" %
            (destination, completed.stderr[-2000:]))
    resolved = kblib.run_cambium_subprocess([bindings["CAMBIUM_RENDER_NODE"], "-e",
        "process.stdout.write(require(process.argv[1]).chromium.executablePath())", str(package)],
        env=environment, text=True, capture_output=True, timeout=30, check=False)
    browser = Path(resolved.stdout.strip())
    if resolved.returncode or not browser.is_absolute() or not browser.resolve().is_relative_to(destination):
        raise runtime.StaticRenderRuntimeError("Playwright did not resolve its managed Chromium")
    if not browser.is_file() or not os.access(browser, os.X_OK):
        raise runtime.StaticRenderRuntimeError("Managed Chromium executable is unavailable")
    return str(browser.resolve())


def prepare_runtime(root, *, apply=False, constructs=()):
    """Discover, optionally prepare, smoke-test, and publish local bindings."""
    root = Path(root).resolve()
    demand = runtime.rendering_request(root, constructs)
    require_browser = demand["requires_browser"]
    target = runtime.default_runtime_bindings_path(root)
    if target.resolve().is_relative_to(root) or any(p.is_symlink() for p in (target, *target.parents)):
        raise runtime.StaticRenderRuntimeError("Rendering cache must be Host-owned outside the repository")
    probe = runtime.probe_runtime(root, require_browser=require_browser)
    result = dict(probe, capability_id=CAPABILITY_ID, request=demand,
                  bindings_path=str(target), smoke=None, created=[], published=False, read_back=False)
    result["preparation_scope"] = {"cache": str(target.parent),
        "binding": str(target), "node_archive": None,
        "npm_lock": runtime.runtime_requirements(root)["package_lock_sha256"],
        "browser": "locked-playwright" if require_browser else None}
    node = probe["bindings"].get("CAMBIUM_RENDER_NODE")
    needs_node = not node or (not probe["bindings"].get("CAMBIUM_RENDER_NODE_MODULES")
                             and not node_runtime.npm_cli(node))
    if needs_node and probe["result"] != "invalid":
        if node and os.environ.get("CAMBIUM_RENDER_NODE"):
            result.update(result="invalid", findings=["Explicit Node has no paired npm; configure its Host binding"],
                diagnostics=[{"code": "explicit-binding-unavailable", "resource": node,
                              "remedy": "configure", "capability_id": CAPABILITY_ID}])
            return result
        result["preparation_scope"]["node_archive"] = node_runtime.node_requirement(root)
    if not apply or probe["result"] == "invalid":
        return result
    try:
        return _prepare_observed(root, target, result, needs_node)
    except (HostEnvironmentUnavailable, OSError, ValueError, KeyError, TypeError,
            subprocess.SubprocessError) as exc:
        return preparation_failure(result, exc, capability_id=CAPABILITY_ID)


def _prepare_observed(root, target, result, needs_node):
    """Apply the observed demand, retaining every completed side effect."""
    demand = result["request"]
    require_browser = demand["requires_browser"]
    expected_before = target.read_bytes() if target.is_file() else None
    bindings = dict(result["bindings"])
    requirement = runtime.runtime_requirements(root)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if needs_node:
        bindings["CAMBIUM_RENDER_NODE"] = node_runtime.prepare_node(root, target.parent, created=result["created"])
    if not bindings.get("CAMBIUM_RENDER_NODE_MODULES"):
        _installation_inputs(requirement)
        npm = node_runtime.npm_cli(bindings["CAMBIUM_RENDER_NODE"])
        if not npm:
            raise HostEnvironmentUnavailable("Paired npm is unavailable", capability_id=CAPABILITY_ID,
                code="npm-unavailable", resource=bindings["CAMBIUM_RENDER_NODE"])
        # A distinct directory is never reused/overwritten after a failed install.
        install = Path(tempfile.mkdtemp(prefix="npm-", dir=str(target.parent)))
        result["created"].append(str(install))
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
                bindings["CAMBIUM_RENDER_NODE"], npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund",
                "--registry=https://registry.npmjs.org", "--strict-ssl=true"],
                cwd=str(install), env=environment, text=True, capture_output=True,
                timeout=300, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise runtime.StaticRenderRuntimeError("npm preparation failed; unselected cache retained at %s: %s" % (install, exc)) from exc
        if completed.returncode:
            raise runtime.StaticRenderRuntimeError("npm preparation failed; unselected cache retained at %s: %s" %
                                                  (install, completed.stderr[-2000:]))
        bindings["CAMBIUM_RENDER_NODE_MODULES"] = str(install / "node_modules")
    if require_browser and not bindings.get("CAMBIUM_RENDER_BROWSER"):
        bindings["CAMBIUM_RENDER_BROWSER"] = _install_browser(root, target.parent, bindings, created=result["created"])
    # An exit code is insufficient: resolve actual imports and, when needed,
    # launch the real browser to render synthetic diagram/math/table constructs.
    result["smoke"] = runtime.verify_runtime_bindings(root, bindings, constructs=demand["constructs"])
    _publish_bindings(root, target, bindings, expected_before=expected_before, report=result)
    verified = runtime.read_runtime_bindings(root, target)
    result.update(result="ready", findings=[], diagnostics=[], bindings=verified)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--apply", action="store_true", help="Explicitly authorize bounded Host-cache installation")
    parser.add_argument("--construct", action="append", default=[],
                        help="Registered construct to actually compile/lay out; repeat as needed; absent means parser only")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = prepare_runtime(args.root, apply=args.apply, constructs=args.construct)
    except HostEnvironmentUnavailable as exc:
        result = {"result": "needs-preparation", "capability_id": CAPABILITY_ID,
                  "findings": [str(exc)], "bindings": {},
                  "diagnostics": [exc.diagnostic()]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {"result": "invalid", "capability_id": CAPABILITY_ID,
                  "findings": [str(exc)], "bindings": {}}
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else
          result["result"] + ": " + "; ".join(result["findings"]))
    return 0 if result["result"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
