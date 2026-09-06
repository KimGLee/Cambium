"""Read-only Host toolchain selection shared by bootstrap and consumers.

No installation, Profile evaluation, task state or ambient shell commands.
The files below remain the unique dependency owners; bindings are local values.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from Tools.platform.common import kblib
from Tools.platform.common.host_environment import HostEnvironmentUnavailable, PREPARATION_CAPABILITY_ID


CAPABILITY_ID = PREPARATION_CAPABILITY_ID
PYTHON_ENV = "CAMBIUM_HOST_PYTHON"
CUE_ENV = "CAMBIUM_CUE"


def requirements(root):
    """Read pinned package and evaluator requirements without importing either."""
    root = Path(root)
    files = ("Tools/requirements-profile.txt", "Tools/requirements-host.txt",
             "Tools/governance/profile/cue-toolchain.json")
    contents = {name: (root / name).read_bytes() for name in files}
    packages, profile_packages = {}, {}
    for name in files[:2]:
        for line in contents[name].decode("utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*==[0-9]+(?:\.[0-9]+){1,3}", line):
                raise ValueError("Host requirements must contain only exact package pins")
            package, version = line.split("==")
            if package in packages:
                raise ValueError("Duplicate Host dependency owner: " + package)
            packages[package] = version
            if name.endswith("requirements-profile.txt"):
                profile_packages[package] = version
    cue = json.loads(contents[files[2]])
    if set(cue) != {"version", "release_base", "archives"} or not isinstance(cue["archives"], dict):
        raise ValueError("Invalid CUE toolchain contract")
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in contents.items()}
    key = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return {"packages": packages, "profile_packages": profile_packages,
            "cue": cue, "source_hashes": hashes, "key": key}


def binding_path(root):
    base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    if not base.is_absolute():
        raise ValueError("Host cache root must be absolute")
    return base / "cambium" / "toolchains" / requirements(root)["key"] / "bindings.json"


def binding_document(root, path=None):
    """Read mechanical binding shape; damaged resources are checked separately."""
    target = Path(path) if path is not None else binding_path(root)
    if not target.is_absolute() or target.resolve().is_relative_to(Path(root).resolve()) or \
            any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError("Toolchain binding must be a regular Host-owned path outside the repository")
    if not target.exists():
        if path is not None:
            raise ValueError("Explicit toolchain binding does not exist")
        return None
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"schema_version", "source_hashes", "python", "cue"} or \
            type(data["schema_version"]) is not int or data["schema_version"] != 1 or \
            data["source_hashes"] != requirements(root)["source_hashes"]:
        raise ValueError("Toolchain binding shape or source identity differs")
    for name in ("python", "cue"):
        if not isinstance(data[name], str) or not Path(data[name]).is_absolute() or "\x00" in data[name]:
            raise ValueError("Toolchain executable binding must be absolute")
    return data


def _run(executable, arguments):
    path = Path(executable)
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise HostEnvironmentUnavailable("Host executable unavailable", capability_id=CAPABILITY_ID,
            code="toolchain-executable-unavailable", resource=str(path))
    try:
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        result = kblib.run_cambium_subprocess([str(path), *arguments], env=environment,
            capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        raise HostEnvironmentUnavailable(str(exc), capability_id=CAPABILITY_ID,
            code="toolchain-execution-unavailable", resource=str(path)) from exc
    if result.returncode:
        raise HostEnvironmentUnavailable("Host toolchain probe failed: " + result.stderr[-1200:],
            capability_id=CAPABILITY_ID, code="toolchain-probe-failed", resource=str(path))
    return result.stdout


def verify_python(executable, packages):
    """Probe only fixed module/version observations, never caller-supplied code."""
    source = ("import json,sys,importlib,importlib.metadata as m\n"
              "packages={}\nfor k in json.loads(sys.argv[1]):\n"
              " try:\n  importlib.import_module(k.replace('-','_'))\n  packages[k]=m.version(k)\n"
              " except (ImportError,m.PackageNotFoundError): packages[k]=None\n"
              "print(json.dumps({'python':list(sys.version_info[:3]),'packages':packages}))")
    value = json.loads(_run(executable, ["-I", "-B", "-c", source, json.dumps(sorted(packages))]))
    if value["python"] < [3, 10, 0] or value["packages"] != packages:
        raise HostEnvironmentUnavailable("Python or package versions do not meet the Tool requirements",
            capability_id=CAPABILITY_ID, code="python-toolchain-mismatch", resource=executable)
    return value


def verify_cue(executable, version):
    output = _run(executable, ["version"])
    if not cue_version_matches(output, version):
        raise HostEnvironmentUnavailable("CUE evaluator version differs", capability_id=CAPABILITY_ID,
            code="cue-version-mismatch", resource=executable)
    return {"version": version}


def cue_version_matches(output, version):
    """One version acceptance predicate for evaluator, observer and installer."""
    return bool(output.splitlines()) and output.splitlines()[0] == "cue version " + version


def cue_unavailable(message, *, code, resource=None):
    """An explicit evaluator needs configuration, not implicit replacement."""
    return HostEnvironmentUnavailable(message, capability_id=CAPABILITY_ID,
        code=code, resource=resource, remedy="configure" if CUE_ENV in os.environ else "prepare")


def select_cue(root):
    """Explicit override wins even when broken; no fallback can mask it."""
    explicit = os.environ.get(CUE_ENV)
    if explicit is not None:
        if not explicit or not Path(explicit).is_absolute():
            raise HostEnvironmentUnavailable("Explicit CUE binding must be an absolute executable path",
                capability_id=CAPABILITY_ID, code="cue-binding-invalid", resource=explicit, remedy="configure")
        return explicit
    try:
        document = binding_document(root)
    except (OSError, ValueError) as exc:
        raise HostEnvironmentUnavailable("Host toolchain binding cannot be consumed: " + str(exc),
            capability_id=CAPABILITY_ID, code="toolchain-binding-invalid",
            resource="Host toolchain binding", remedy="configure") from exc
    return document["cue"] if document is not None else shutil.which("cue")


def observe(root, *, path=None, current_process=False, configuration=False):
    """Describe actual resources without installing or declaring governance ready."""
    request = requirements(root)
    required_packages = request["packages"] if configuration else request["profile_packages"]
    document = binding_document(root, path)
    bindings = {
        "python": (sys.executable if current_process else os.environ.get(PYTHON_ENV,
                   document["python"] if document else sys.executable)),
        "cue": os.environ.get(CUE_ENV, document["cue"] if document else shutil.which("cue")),
    }
    sources = {name: "process" if name == "python" and current_process else
               "explicit" if variable in os.environ else
               "managed" if document else "discovered"
               for name, variable in (("python", PYTHON_ENV), ("cue", CUE_ENV))}
    verified, diagnostics = {}, []
    for name, value in bindings.items():
        try:
            if not value:
                raise HostEnvironmentUnavailable("Missing " + name, capability_id=CAPABILITY_ID,
                    code="toolchain-not-found", resource=name)
            verified[name] = (verify_python(value, required_packages) if name == "python"
                              else verify_cue(value, request["cue"]["version"]))
        except HostEnvironmentUnavailable as exc:
            if sources[name] == "explicit":
                exc.remedy = "configure"
            diagnostics.append(dict(exc.diagnostic(), component=name))
    return {"request": request, "required_packages": required_packages, "bindings": bindings, "sources": sources,
            "verified": verified, "diagnostics": diagnostics,
            "result": "ready" if not diagnostics else "needs-preparation"}


__all__ = ["CAPABILITY_ID", "CUE_ENV", "requirements", "binding_path",
           "binding_document", "verify_python", "verify_cue", "cue_version_matches", "cue_unavailable", "select_cue", "observe"]
