"""Merge one generated Cambium Host registration, preserving other settings.

The generator owns product shape. This adapter owns only bounded installation
and comparison. No MCP, environment installation, service restart or adoption.
"""

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile

from Tools.platform.agent_interface import render_host_configs as generator
from Tools.platform.common.host_environment import HostEnvironmentUnavailable
from Tools.platform.common.host_environment import preparation_failure
from Tools.knowledge.rendering.static_render_runtime import RUNTIME_ENV_KEYS


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate Host JSON key: " + key)
        result[key] = value
    return result


def _toml():
    try:
        import tomlkit
    except ImportError as exc:
        raise HostEnvironmentUnavailable("Host editing toolchain is unavailable",
            capability_id="host-environment-preparation-v1", code="host-editor-unavailable",
            resource="Tools/requirements-host.txt") from exc
    return tomlkit


def _merge_map(current, desired, *, replace_overrides):
    if not isinstance(current, dict) or not isinstance(desired, dict):
        raise ValueError("Host server registration must be a mapping")
    merged = copy.deepcopy(current)
    if replace_overrides and "env" in merged:
        if not isinstance(merged["env"], dict):
            raise ValueError("Host environment must be a mapping")
        for name in RUNTIME_ENV_KEYS:
            if name not in desired.get("env", {}):
                merged["env"].pop(name, None)
    for key, value in desired.items():
        if key == "env":
            environment = merged.setdefault("env", {})
            if not isinstance(environment, dict):
                raise ValueError("Host environment must be a mapping")
            for name, binding in value.items():
                if name == "CAMBIUM_CUE" and name in environment and not replace_overrides:
                    continue
                environment[name] = binding
        elif key == "command" and key in merged and not replace_overrides:
            continue
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def merge_product(host, before, generated, *, replace_overrides=False):
    """Pure byte transform. Returns unchanged bytes for an already-current entry."""
    kind = generator.HOSTS[host]["format"]
    if kind == "json":
        old = json.loads(before or "{}", object_pairs_hook=_json_object)
        expected = json.loads(generated, object_pairs_hook=_json_object)
        key = "mcpServers"
        if not isinstance(old, dict) or not isinstance(old.get(key, {}), dict):
            raise ValueError("Host MCP servers must be a mapping")
        result = copy.deepcopy(old)
        servers = result.setdefault(key, {})
        servers[generator.SERVER_NAME] = _merge_map(servers.get(generator.SERVER_NAME, {}),
            expected[key][generator.SERVER_NAME], replace_overrides=replace_overrides)
        return before if result == old else json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if kind == "toml":
        codec = _toml()
        old = codec.parse(before or "")
        expected = codec.parse(generated)
        servers = old.setdefault("mcp_servers", codec.table())
        if not hasattr(servers, "items"):
            raise ValueError("Host MCP servers must be a table")
        name = generator.SERVER_NAME
        existing = servers.setdefault(name, codec.table())
        if not hasattr(existing, "unwrap"):
            raise ValueError("Cambium MCP server must be a table")
        target = _merge_map(existing.unwrap(), expected["mcp_servers"][name].unwrap(),
                            replace_overrides=replace_overrides)
        if existing.unwrap() == target:
            return before
        for key, value in target.items():
            if key == "env" and key in existing:
                for env_key in list(existing[key]):
                    if env_key not in value:
                        del existing[key][env_key]
                for env_key, env_value in value.items():
                    existing[key][env_key] = env_value
            else:
                existing[key] = value
        return codec.dumps(old)
    if kind == "dotenv":
        desired = generator.parse_dotenv(generated)
        seen, output = set(), []
        for line in before.splitlines(keepends=True):
            content = line.strip()
            if not content or content.startswith("#"):
                output.append(line)
                continue
            name, separator, _value = content.partition("=")
            name = name.strip()
            if separator and replace_overrides and name in RUNTIME_ENV_KEYS and name not in desired:
                continue
            if not separator or name not in desired:
                output.append(line)
                continue
            if name in seen:
                raise ValueError("Repeated managed dotenv binding: " + name)
            seen.add(name)
            if name == "CAMBIUM_CUE" and not replace_overrides:
                output.append(line)
            else:
                output.append(generator.dotenv_lines({name: desired[name]})[0] + "\n")
        if output and not output[-1].endswith("\n"):
            output[-1] += "\n"
        output.extend(line + "\n" for line in generator.dotenv_lines(
            {name: value for name, value in desired.items() if name not in seen}))
        return "".join(output)
    raise ValueError("This product is a Host-native patch; apply it through the declared Host mechanism")


def install(host, generated, destination, *, apply=False, expected_before=None, replace_overrides=False):
    """Preview first, then require that exact before-image for a bounded write."""
    target = Path(destination).absolute()
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError("Host configuration must not traverse a symlink")
    if ".cambium" in target.parts:
        raise ValueError("Host configuration cannot be installed in adopter runtime")
    before_bytes = target.read_bytes() if target.exists() else None
    before = before_bytes.decode("utf-8") if before_bytes is not None else ""
    after = merge_product(host, before, generated, replace_overrides=replace_overrides)
    identity = hashlib.sha256(before_bytes).hexdigest() if before_bytes is not None else "absent"
    report = {"destination": str(target), "before_sha256": identity,
              "after_sha256": hashlib.sha256(after.encode()).hexdigest(),
              "changed": after != before, "installed": after == before,
              "published": False, "read_back": after == before,
              "retained_overrides": merge_product(host, after, generated, replace_overrides=True) != after,
              "consumer_observed": False, "reload": "host-dependent"}
    if not apply or after == before:
        return report
    if expected_before != identity:
        raise ValueError("Host configuration changed or lacks an approved preview")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, stage = tempfile.mkstemp(prefix=".cambium-host-", dir=target.parent)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(after)
        output.flush()
        os.fsync(output.fileno())
    if target.is_symlink() or any(p.is_symlink() for p in target.parents) or \
            (target.read_bytes() if target.exists() else None) != before_bytes:
        raise ValueError("Host configuration changed before publication")
    if target.exists():
        os.chmod(stage, target.stat().st_mode & 0o777)
    try:
        os.replace(stage, target)
        report["published"] = True
        if target.read_bytes() != after.encode():
            raise ValueError("Host configuration read-back differs")
    except (OSError, ValueError) as exc:
        return preparation_failure(report, exc, capability_id="host-environment-preparation-v1")
    report["installed"] = True
    report["read_back"] = True
    return report


__all__ = ["install"]
