"""Host-bound, offline rendering with source-bound artifacts, not attestations.

The official remark AST is the only selector. This adapter owns execution
and integrity checks; K12/Profile own applicability and acceptance bindings.
"""
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import Tools.platform.common.kblib as kblib


SELECTOR_ID = "remark-commonmark-gfm-math-v1"
CAPABILITY_ID = "static-markdown-render-v1"
_OWNER = Path("Tools/knowledge/rendering")
RUNTIME_ENV_KEYS = ("CAMBIUM_RENDER_NODE", "CAMBIUM_RENDER_BROWSER",
                    "CAMBIUM_RENDER_NODE_MODULES")


class StaticRenderRuntimeError(ValueError):
    """Required renderer implementation, dependencies, or Host binding missing."""


def _sha(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _json_sha(value):
    return _sha(json.dumps(value, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":")).encode("utf-8"))


@lru_cache(maxsize=128)
def _hash_file_version(path_string, identity):
    path = Path(path_string)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _file_sha(path):
    stat = path.stat()
    return _hash_file_version(str(path.resolve()),
        (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))


def _owner(root):
    return Path(root).resolve() / _OWNER


def _capability(root):
    from Tools.governance.profile.rendering_contract import load_rendering_capabilities
    record = load_rendering_capabilities(root).get(CAPABILITY_ID)
    if record is None or record["selector_id"] != SELECTOR_ID or \
            record["implementation_path"] != str(_OWNER / "static_render_runtime.py"):
        raise StaticRenderRuntimeError("Renderer implementation differs from registered capability")
    return record


def _acceptances(root):
    return {row["construct"]: row["acceptance"]
            for row in _capability(root)["acceptance_bindings"]}


def _executable(name, value=None):
    value = value or os.environ.get(name)
    if not value or not Path(value).is_absolute():
        raise StaticRenderRuntimeError("%s must bind an absolute executable" % name)
    path = Path(value).resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise StaticRenderRuntimeError("%s executable is unavailable" % name)
    return path


def runtime_requirements(root):
    """Read the existing capability and npm owners; never invent version policy."""
    capability = _capability(root)
    directory = _owner(root) / "static_renderer"
    manifest = directory / "package.json"
    lock = directory / "package-lock.json"
    if not manifest.is_file() or not lock.is_file():
        raise StaticRenderRuntimeError("Tool renderer manifest/lockfile missing")
    package = json.loads(manifest.read_text(encoding="utf-8"))
    locked = json.loads(lock.read_text(encoding="utf-8"))
    if locked.get("lockfileVersion") != 3 or not isinstance(locked.get("packages"), dict):
        raise StaticRenderRuntimeError("Renderer needs an npm v3 package lock")
    for field in ("name", "version", "dependencies", "engines"):
        if locked["packages"].get("", {}).get(field) != package.get(field):
            raise StaticRenderRuntimeError("Renderer manifest and lock disagree: " + field)
    minimum = re.fullmatch(r">=(\d+)", package.get("engines", {}).get("node", ""))
    if minimum is None:
        raise StaticRenderRuntimeError("Unsupported renderer Node engine constraint")
    return {"capability_id": capability["capability_id"],
            "manifest": str(manifest), "lock": str(lock),
            "package_sha256": _file_sha(manifest),
            "package_lock_sha256": _file_sha(lock),
            "node_engine": package["engines"]["node"],
            "node_minimum_major": int(minimum.group(1)),
            "dependencies": package["dependencies"], "packages": locked["packages"]}


def default_runtime_bindings_path(root):
    """Return a Host-user path keyed by the authoritative dependency lock."""
    cache = os.environ.get("XDG_CACHE_HOME")
    base = Path(cache) if cache and Path(cache).is_absolute() else Path.home() / ".cache"
    lock = runtime_requirements(root)["package_lock_sha256"].split(":", 1)[1]
    return base / "cambium" / "rendering" / lock / "bindings.json"


def _dependencies(root, modules=None):
    requirement = runtime_requirements(root)
    modules = Path(modules or _resolve_bindings(root)["CAMBIUM_RENDER_NODE_MODULES"]).resolve()
    if not modules.is_dir():
        raise StaticRenderRuntimeError("Pinned renderer node_modules missing; run npm ci for the Tool lockfile")
    if _file_sha(modules.parent / "package.json") != requirement["package_sha256"] or \
            _file_sha(modules.parent / "package-lock.json") != requirement["package_lock_sha256"]:
        raise StaticRenderRuntimeError("Host dependency manifest/lock differs from Tool")
    declared = requirement["dependencies"]
    installed = {}
    for name, version in sorted(declared.items()):
        package = modules / name / "package.json"
        if not package.is_file():
            raise StaticRenderRuntimeError("Missing pinned renderer dependency: %s" % name)
        actual = json.loads(package.read_text(encoding="utf-8"))["version"]
        if actual != version:
            raise StaticRenderRuntimeError("Renderer dependency version differs: %s" % name)
        installed[name] = actual
    for relative, row in requirement["packages"].items():
        if not relative:
            continue
        package = modules.parent / relative / "package.json"
        if not package.resolve().is_relative_to(modules):
            raise StaticRenderRuntimeError("Renderer dependency escapes its bound directory")
        if not package.is_file() and row.get("optional"):
            continue
        if not package.is_file() or json.loads(package.read_text(encoding="utf-8")).get("version") != row.get("version"):
            raise StaticRenderRuntimeError("Locked renderer dependency differs: " + relative)
    return modules, {"package_sha256": requirement["package_sha256"],
                     "package_lock_sha256": requirement["package_lock_sha256"],
                     "installed_versions": installed}


def _validate_bindings(root, bindings, *, check_executables=True):
    if not isinstance(bindings, dict) or set(bindings) - set(RUNTIME_ENV_KEYS):
        raise StaticRenderRuntimeError("Invalid rendering Host binding keys")
    required = {"CAMBIUM_RENDER_NODE", "CAMBIUM_RENDER_NODE_MODULES"}
    if not required <= set(bindings):
        raise StaticRenderRuntimeError("Rendering Host bindings need Node and dependencies")
    if any(not isinstance(value, str) or not Path(value).is_absolute() for value in bindings.values()):
        raise StaticRenderRuntimeError("Rendering Host bindings must be absolute paths")
    requirement = runtime_requirements(root)
    if check_executables:
        node = _executable("CAMBIUM_RENDER_NODE", bindings["CAMBIUM_RENDER_NODE"])
        version = _version(node)
        match = re.fullmatch(r"v(\d+)\.\d+\.\d+(?:[-+].*)?", version)
        if match is None or int(match.group(1)) < requirement["node_minimum_major"]:
            raise StaticRenderRuntimeError("Node does not satisfy " + requirement["node_engine"])
    _dependencies(root, bindings["CAMBIUM_RENDER_NODE_MODULES"])
    if check_executables and bindings.get("CAMBIUM_RENDER_BROWSER"):
        browser = _executable("CAMBIUM_RENDER_BROWSER", bindings["CAMBIUM_RENDER_BROWSER"])
        if not re.search(r"(?:Chrome|Chromium|Edge)\s", _version(browser)):
            raise StaticRenderRuntimeError("Renderer requires a Chromium-family browser")
    return {key: str(Path(value).resolve()) for key, value in bindings.items()}


def read_runtime_bindings(root, path=None, *, check_executables=True):
    """Read a checked Host projection; absent default bindings are harmless.

    Only local discovery/preparation may defer executable validation so moved
    binaries can be rediscovered. Schema, lock and dependencies always validate.
    Host publication and actual rendering use the strict default.
    """
    target = Path(path) if path is not None else default_runtime_bindings_path(root)
    if target.resolve().is_relative_to(Path(root).resolve()):
        raise StaticRenderRuntimeError("Rendering Host binding file must be outside the repository")
    if not target.exists() and not target.is_symlink() and path is None:
        return {}
    try:
        if not target.is_absolute() or target.is_symlink() or not target.is_file():
            raise StaticRenderRuntimeError("Rendering Host binding file must be an absolute regular file")
        document = json.loads(target.read_text(encoding="utf-8"))
        requirement = runtime_requirements(root)
        if set(document) != {"schema_version", "capability_id", "package_sha256",
                             "package_lock_sha256", "bindings"} or \
                type(document["schema_version"]) is not int or document["schema_version"] != 1:
            raise StaticRenderRuntimeError("Invalid rendering Host binding document")
        for key in ("capability_id", "package_sha256", "package_lock_sha256"):
            if document[key] != requirement[key]:
                raise StaticRenderRuntimeError("Rendering Host bindings are stale: " + key)
        return _validate_bindings(root, document["bindings"], check_executables=check_executables)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise StaticRenderRuntimeError("Cannot read rendering Host bindings: %s" % exc) from exc


def _discover_executable(name):
    candidates = [shutil.which(name)]
    if name == "node":
        candidates.extend(["/opt/homebrew/bin/node", "/usr/local/bin/node", "/usr/bin/node"])
    else:
        candidates.extend(shutil.which(value) for value in (
            "google-chrome", "chromium", "chromium-browser", "msedge"))
        candidates.extend(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"])
    return [str(Path(value).resolve()) for value in candidates
            if value and Path(value).is_file() and os.access(value, os.X_OK)]


def probe_runtime(root, *, require_browser=False):
    """Read-only capability discovery. Never install or create runtime state."""
    bindings, findings = {}, []
    try:
        requirement = runtime_requirements(root)
        explicit = {key: os.environ[key] for key in RUNTIME_ENV_KEYS if os.environ.get(key)}
        required = {"CAMBIUM_RENDER_NODE", "CAMBIUM_RENDER_NODE_MODULES"}
        if require_browser:
            required.add("CAMBIUM_RENDER_BROWSER")
        if not required <= set(explicit):
            bindings.update(read_runtime_bindings(root, check_executables=False))
        bindings.update(explicit)
        for key, value in explicit.items():
            if not Path(value).is_absolute():
                raise StaticRenderRuntimeError(key + " must bind an absolute path")
        for key, name in (("CAMBIUM_RENDER_NODE", "node"),
                          ("CAMBIUM_RENDER_BROWSER", "chrome")):
            candidates = ([bindings[key]] if bindings.get(key) else [])
            if key not in explicit:
                candidates.extend(_discover_executable(name))
            valid = None
            for candidate in candidates:
                try:
                    executable = _executable(key, candidate)
                    version = _version(executable)
                    if name == "node":
                        match = re.fullmatch(r"v(\d+)\.\d+\.\d+(?:[-+].*)?", version)
                        if not match or int(match.group(1)) < requirement["node_minimum_major"]:
                            raise StaticRenderRuntimeError("Node does not satisfy " + requirement["node_engine"])
                    elif not re.search(r"(?:Chrome|Chromium|Edge)\s", version):
                        raise StaticRenderRuntimeError("Unsupported Chromium-family browser")
                    valid = str(executable)
                    break
                except (OSError, StaticRenderRuntimeError, subprocess.SubprocessError):
                    if key in explicit:
                        raise
            if valid:
                bindings[key] = valid
            else:
                bindings.pop(key, None)
                if name == "node" or require_browser:
                    findings.append(key + " unavailable or incompatible")
        modules = bindings.get("CAMBIUM_RENDER_NODE_MODULES") or str(
            _owner(root) / "static_renderer/node_modules")
        if Path(modules).is_dir():
            _dependencies(root, modules)
            bindings["CAMBIUM_RENDER_NODE_MODULES"] = str(Path(modules).resolve())
        elif "CAMBIUM_RENDER_NODE_MODULES" in explicit:
            raise StaticRenderRuntimeError("Explicit renderer dependency directory is unavailable")
        else:
            findings.append("Pinned renderer dependencies are not prepared")
        return {"result": "needs-preparation" if findings else "ready",
                "bindings": bindings, "findings": findings}
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        return {"result": "invalid", "bindings": bindings, "findings": [str(exc)]}


def _resolve_bindings(root, *, require_browser=False):
    probe = probe_runtime(root, require_browser=require_browser)
    if probe["result"] != "ready":
        raise StaticRenderRuntimeError("; ".join(probe["findings"]))
    return probe["bindings"]


@lru_cache(maxsize=16)
def _version_probe(executable, digest):
    result = kblib.run_cambium_subprocess([str(executable), "--version"], capture_output=True,
                            text=True, timeout=15, check=False)
    if result.returncode or not result.stdout.strip():
        raise StaticRenderRuntimeError("Runtime version probe failed: %s" % executable)
    return result.stdout.strip()


def _version(executable):
    return _version_probe(str(executable), _file_sha(executable))


def current_runtime_fingerprint(*, root):
    """Probe current binaries/lock/config without starting a rendering browser."""
    bindings = _resolve_bindings(root, require_browser=True)
    node = Path(bindings["CAMBIUM_RENDER_NODE"])
    browser = Path(bindings["CAMBIUM_RENDER_BROWSER"])
    modules, dependency = _dependencies(root, bindings["CAMBIUM_RENDER_NODE_MODULES"])
    owner = _owner(root)
    config = {"node": str(node), "browser": str(browser), "node_modules": str(modules)}
    return {
        "capability_id": CAPABILITY_ID, "selector_id": SELECTOR_ID,
        "capability_sha256": _json_sha(_capability(root)),
        "implementation_sha256": _file_sha(owner / "static_markdown_renderer.mjs"),
        "adapter_sha256": _file_sha(owner / "static_render_runtime.py"),
        "dependencies": dependency, "host_config": config,
        "host_config_sha256": _json_sha(config),
        "node_sha256": _file_sha(node), "node_version": _version(node),
        "browser_sha256": _file_sha(browser), "browser_version": _version(browser),
    }


def _invoke(request, *, root, timeout=120, runtime_bindings=None):
    bindings = (_validate_bindings(root, runtime_bindings) if runtime_bindings is not None
                else _resolve_bindings(root, require_browser=request.get("action") == "render"))
    node = Path(bindings["CAMBIUM_RENDER_NODE"])
    modules, _ = _dependencies(root, bindings["CAMBIUM_RENDER_NODE_MODULES"])
    script = _owner(root) / "static_markdown_renderer.mjs"
    if not script.is_file():
        raise StaticRenderRuntimeError("Static renderer implementation missing")
    environment = dict(os.environ)
    environment.pop("NODE_PATH", None)
    environment.pop("NODE_OPTIONS", None)
    environment["CAMBIUM_RENDER_NODE_MODULES"] = str(modules)
    try:
        completed = kblib.run_cambium_subprocess([str(node), str(script)],
            input=json.dumps(request, ensure_ascii=False), text=True,
            encoding="utf-8", capture_output=True, check=False, timeout=timeout,
            env=environment)
        value = json.loads(completed.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise StaticRenderRuntimeError("Renderer invocation failed: %s" % exc) from exc
    if completed.returncode:
        raise StaticRenderRuntimeError("Renderer failed: %s" %
            "; ".join(value.get("diagnostics", [completed.stderr[:2000]])))
    return value


def verify_runtime_bindings(root, bindings, *, require_browser=False):
    """Exercise only a synthetic Host smoke input, never corpus or Receipt writes."""
    source = "```mermaid\nflowchart LR\nA --> B\n```\n\n$x+1$\n\n| A | B |\n|---|---|\n| a | b |\n"
    action = "render" if require_browser else "select"
    request = {"action": action, "source": source}
    if require_browser:
        if not bindings.get("CAMBIUM_RENDER_BROWSER"):
            raise StaticRenderRuntimeError("CAMBIUM_RENDER_BROWSER is required for rendering smoke")
        request.update({"browser": bindings["CAMBIUM_RENDER_BROWSER"],
                        "bindings": _acceptances(root)})
    result = _invoke(request, root=root, runtime_bindings=bindings)
    if result.get("selector_id") != SELECTOR_ID or result.get("source_sha256") != _sha(source.encode()):
        raise StaticRenderRuntimeError("Rendering smoke is not bound to the requested source")
    if require_browser and (result.get("result") != "pass" or result.get("diagnostics")):
        raise StaticRenderRuntimeError("Rendering smoke failed: " + str(result.get("diagnostics")))
    if not result.get("constructs"):
        raise StaticRenderRuntimeError("Rendering smoke produced no parsed constructs")
    return {"action": action, "result": "pass", "source_sha256": result["source_sha256"]}


@lru_cache(maxsize=256)
def _select_cached(text, root, fingerprint):
    return json.dumps(_invoke({"action": "select", "source": text}, root=root),
                      ensure_ascii=False, sort_keys=True)


def _select_inventory(text, *, root):
    if not isinstance(text, str):
        raise StaticRenderRuntimeError("Markdown source must be text")
    bindings = _resolve_bindings(root)
    node = Path(bindings["CAMBIUM_RENDER_NODE"])
    modules, dependency = _dependencies(root, bindings["CAMBIUM_RENDER_NODE_MODULES"])
    owner = _owner(root)
    fingerprint = _json_sha({"node": str(node), "node_sha256": _file_sha(node),
        "node_modules": str(modules), "dependencies": dependency,
        "capability_sha256": _json_sha(_capability(root)),
        "implementation_sha256": _file_sha(owner / "static_markdown_renderer.mjs"),
        "adapter_sha256": _file_sha(owner / "static_render_runtime.py")})
    result = json.loads(_select_cached(text, str(Path(root).resolve()), fingerprint))
    if result.get("selector_id") != SELECTOR_ID or \
            result.get("source_sha256") != _sha(text.encode("utf-8")):
        raise StaticRenderRuntimeError("Selector output is not bound to its source")
    constructs = result.get("constructs")
    if not isinstance(constructs, list) or constructs != sorted(set(constructs)) or \
            any(value not in _acceptances(root) for value in constructs):
        raise StaticRenderRuntimeError("Selector returned invalid construct identities")
    return result


def select_constructs(text, *, root):
    return tuple(_select_inventory(text, root=root)["constructs"])


def _bindings(bindings, root):
    allowed = _acceptances(root)
    if not isinstance(bindings, dict) or any(
            key not in allowed or value != allowed[key]
            for key, value in bindings.items()):
        raise StaticRenderRuntimeError("Renderer bindings must use exact registered acceptance IDs")
    return dict(sorted(bindings.items()))


def render_page(text, *, target, bindings, root):
    """Return actual SVG/HTML artifacts inline for the existing evidence CAS."""
    if not isinstance(text, str) or not isinstance(target, str) or not target:
        raise StaticRenderRuntimeError("Source text and nonempty target are required")
    report = {"schema_version": 1, "target": target,
        "source_sha256": _sha(text.encode("utf-8")), "selector_id": SELECTOR_ID,
        "bindings_sha256": None, "runtime_fingerprint": None, "runtime_sha256": None,
        "constructs": [], "artifacts": [], "result": "fail", "diagnostics": []}
    try:
        normalized = _bindings(bindings, root)
        report["bindings_sha256"] = _json_sha(normalized)
        fingerprint = current_runtime_fingerprint(root=root)
        report["runtime_fingerprint"] = fingerprint
        report["runtime_sha256"] = _json_sha(fingerprint)
        value = _invoke({"action": "render", "source": text, "bindings": normalized,
                         "browser": fingerprint["host_config"]["browser"]}, root=root)
        if value.get("source_sha256") != report["source_sha256"] or value.get("selector_id") != SELECTOR_ID:
            raise StaticRenderRuntimeError("Rendered output is not source-bound")
        for field in ("constructs", "artifacts", "result", "diagnostics"):
            report[field] = value[field]
        # GFM HTML normalizes some malformed rows. The already-admitted Kernel
        # predicate must still reject those sources instead of hiding the loss.
        from Tools.knowledge.rendering.changed_scope_rendering_checks import level1_markdown_table_static
        structural = level1_markdown_table_static(text, target)
        if structural["result"] != "pass":
            report["result"] = "fail"
            report["diagnostics"].append("Kernel table structure failed: " +
                                          json.dumps(structural["diagnostics"], ensure_ascii=False))
        if current_runtime_fingerprint(root=root) != fingerprint:
            raise StaticRenderRuntimeError("Renderer runtime changed during execution")
    except (StaticRenderRuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        report["result"] = "fail"
        report["diagnostics"].append(str(exc))
    report["report_sha256"] = _json_sha(report)
    return report


def validate_render_result(report, text, bindings, *, root):
    """Validate fresh runtime, source, bindings and inline artifacts; no render."""
    errors = []
    try:
        expected_fields = {"schema_version", "target", "source_sha256", "selector_id",
            "bindings_sha256", "runtime_fingerprint", "runtime_sha256", "constructs",
            "artifacts", "result", "diagnostics", "report_sha256"}
        if not isinstance(report, dict) or set(report) != expected_fields or report["schema_version"] != 1:
            return ["Static rendering report fields/version are invalid"]
        core = {key: value for key, value in report.items() if key != "report_sha256"}
        if _json_sha(core) != report["report_sha256"]: errors.append("Rendering report digest differs")
        if report["source_sha256"] != _sha(text.encode("utf-8")): errors.append("Rendering source is stale")
        if report["bindings_sha256"] != _json_sha(_bindings(bindings, root)): errors.append("Rendering bindings are stale")
        if report["selector_id"] != SELECTOR_ID: errors.append("Rendering selector differs")
        current = current_runtime_fingerprint(root=root)
        if report["runtime_fingerprint"] != current or report["runtime_sha256"] != _json_sha(current):
            errors.append("Rendering runtime is stale")
        if report["result"] != "pass" or report["diagnostics"]: errors.append("Rendering did not pass")
        artifacts = {}
        for artifact in report["artifacts"]:
            if set(artifact) != {"artifact_id", "media_type", "content", "sha256"}:
                errors.append("Rendering artifact fields differ"); continue
            if artifact["artifact_id"] in artifacts: errors.append("Rendering artifact identity repeats")
            artifacts[artifact["artifact_id"]] = artifact
            if _sha(artifact["content"].encode("utf-8")) != artifact["sha256"]:
                errors.append("Rendering artifact digest differs")
        inventory = _select_inventory(text, root=root)
        identity_fields = ("kind", "instance_id", "source_range", "source_sha256")
        actual_instances = [{key: item[key] for key in identity_fields}
                            for item in report["constructs"]]
        if actual_instances != inventory["instances"]:
            errors.append("Rendering construct coverage differs")
        used = []
        for item in report["constructs"]:
            if set(item) != {"kind", "instance_id", "source_range", "source_sha256",
                            "acceptance", "result", "artifact_ids", "measurements", "diagnostics"}:
                errors.append("Rendering construct fields differ")
            if item["kind"] not in _acceptances(root) or item["acceptance"] != bindings.get(item["kind"]):
                errors.append("Rendering construct binding differs")
            if item["result"] != "pass" or item["diagnostics"] or not item["artifact_ids"]:
                errors.append("Rendering construct did not pass")
            start, end = item["source_range"]["start"]["offset"], item["source_range"]["end"]["offset"]
            # remark offsets are UTF-16 code units, not Python code points.
            fragment = text.encode("utf-16-le")[start*2:end*2].decode("utf-16-le")
            if _sha(fragment.encode("utf-8")) != item["source_sha256"]:
                errors.append("Rendering construct source differs")
            used.extend(item["artifact_ids"])
        if sorted(used) != sorted(artifacts): errors.append("Rendering artifact coverage differs")
    except (StaticRenderRuntimeError, OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
        errors.append("Invalid rendering evidence: %s" % exc)
    return errors
