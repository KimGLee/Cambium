"""Prepare a private Python package environment and CUE using existing owners."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from Tools.platform.common import host_toolchain, kblib
from Tools.platform.common.host_environment import HostEnvironmentUnavailable, preparation_failure
from Tools.platform.distribution import install_profile_toolchain


def prepare(root, *, apply=False, configuration=False):
    root = Path(root).resolve()
    observation = host_toolchain.observe(root, configuration=configuration)
    target = host_toolchain.binding_path(root)
    # Shape/ownership is checked before creating or touching anything.
    host_toolchain.binding_document(root)
    observation.update(published=False, read_back=False, bindings_path=str(target), created=[],
                       write_scope=str(target.parent))
    if not apply or any(row["remedy"] == "configure" for row in observation["diagnostics"]):
        return observation
    before = target.read_bytes() if target.is_file() else None
    bindings = dict(observation["bindings"])
    requirement = observation["request"]
    packages = observation["required_packages"]
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        if "python" not in observation["verified"]:
            if sys.version_info < (3, 10):
                raise HostEnvironmentUnavailable("Provide Python 3.10 or newer to run bootstrap",
                    capability_id=host_toolchain.CAPABILITY_ID, code="python-bootstrap-unavailable",
                    resource=sys.executable, remedy="provide-host")
            candidate = Path(tempfile.mkdtemp(prefix="python-", dir=target.parent))
            observation["created"].append(str(candidate))
            kblib.run_cambium_subprocess([sys.executable, "-I", "-m", "venv", str(candidate)],
                check=True, capture_output=True, text=True, timeout=120)
            executable = candidate / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            environment = {key: value for key, value in os.environ.items()
                           if not key.upper().startswith("PIP_") and key not in ("PYTHONPATH", "PYTHONHOME")}
            kblib.run_cambium_subprocess([str(executable), "-I", "-m", "pip", "--isolated",
                "install", "--disable-pip-version-check", "--no-input", "--no-deps", "--only-binary=:all:",
                "--index-url", "https://pypi.org/simple",
                *[name + "==" + version for name, version in sorted(packages.items())]],
                env=environment, check=True, capture_output=True, text=True, timeout=300)
            host_toolchain.verify_python(str(executable), packages)
            bindings["python"] = str(executable)
        if "cue" not in observation["verified"]:
            candidate = Path(tempfile.mkdtemp(prefix="cue-", dir=target.parent))
            observation["created"].append(str(candidate))
            bindings["cue"] = install_profile_toolchain.install_cue(candidate, root=root)
        host_toolchain.verify_python(bindings["python"], packages)
        host_toolchain.verify_cue(bindings["cue"], requirement["cue"]["version"])
        document = {"schema_version": 1, "source_hashes": requirement["source_hashes"], **bindings}
        content = (json.dumps(document, sort_keys=True, indent=2) + "\n").encode()
        descriptor, staged = tempfile.mkstemp(prefix="bindings-", suffix=".json", dir=target.parent)
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        host_toolchain.binding_document(root)
        if (target.read_bytes() if target.is_file() else None) != before or \
                host_toolchain.requirements(root) != requirement:
            raise ValueError("Host selection or requirements changed during preparation")
        os.replace(staged, target)
        observation["published"] = True
        actual = host_toolchain.observe(root, path=target, configuration=configuration)
        if actual["result"] != "ready" or actual["bindings"] != bindings:
            raise ValueError("Published Host toolchain read-back differs")
        observation.update(actual, published=True, read_back=True)
    except (OSError, ValueError, subprocess.SubprocessError, HostEnvironmentUnavailable) as exc:
        preparation_failure(observation, exc, capability_id=host_toolchain.CAPABILITY_ID)
    return observation


__all__ = ["prepare"]
