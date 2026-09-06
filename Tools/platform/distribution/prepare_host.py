"""One Host preparation entry; composes providers, never adopts a Profile.

Rendering is opt-in by actual selector/construct demand. A terminal-capable
Host authorizes installation; the MCP surface only observes and hands off.
"""

import argparse
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from Tools.platform.common import host_toolchain, kblib
from Tools.platform.common.host_environment import HostEnvironmentUnavailable, preparation_failure
from Tools.platform.distribution import prepare_host_toolchain, prepare_rendering_runtime
from Tools.platform.agent_interface import render_host_configs, install_host_config
from Tools.platform.agent_interface import tool_availability


def _host_stage(root, workspace, host, toolchain, *, replace_overrides, projection_target):
    """Render through the unique generator; local paths never enter tracked products."""
    parent = root / ".tmp" / "host-preparation"
    if any(path.is_symlink() for path in (parent, *parent.parents)):
        raise ValueError("Host staging cannot traverse a symlink")
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="products-", dir=parent))
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        status = render_host_configs.main([str(root), "--host", host, "--output-dir", str(stage),
            "--distribution-root", str(root), "--workspace-root", str(workspace),
            "--projection-target", projection_target,
            "--toolchain-bindings", toolchain["bindings_path"]])
    if status:
        return preparation_failure({"staging": str(stage), "installed": False},
            ValueError("Host generator refused: " + buffer.getvalue()), capability_id=host_toolchain.CAPABILITY_ID)
    entry = render_host_configs.HOSTS[host]
    product = stage / entry["output"]
    if entry["format"] == "yaml":
        return {"generated": str(product), "installed": False, "consumer_observed": False,
                "next": "Use the declared dsh Host-native patch mechanism"}
    destination = Path(entry["destination"].replace("<corpus>", str(workspace)))
    text = product.read_text(encoding="utf-8")
    try:
        preview = install_host_config.install(host, text, destination, replace_overrides=replace_overrides)
        result = install_host_config.install(host, text, destination, apply=True,
            expected_before=preview["before_sha256"], replace_overrides=replace_overrides)
    except (OSError, ValueError, HostEnvironmentUnavailable) as exc:
        result = preparation_failure({"installed": False}, exc, capability_id=host_toolchain.CAPABILITY_ID)
    return dict(result, generated=str(product))


def prepare(root, *, apply=False, rendering=False, constructs=(), host=None, workspace=None,
            replace_overrides=False, projection_target=tool_availability.SOURCE_DISTRIBUTION):
    root = Path(root).resolve()
    if host is not None and host not in render_host_configs.HOSTS:
        raise ValueError("Unknown Host product")
    workspace = Path(workspace).resolve() if workspace else root
    if not workspace.is_dir():
        raise ValueError("Host workspace does not exist")
    if projection_target not in tool_availability.PROJECTION_TARGETS:
        raise ValueError("Unknown distribution projection target")
    if projection_target == tool_availability.CARRIED_RUNTIME and root != workspace:
        raise ValueError("Carried-runtime distribution and workspace must be identical")
    result = {"capability_id": host_toolchain.CAPABILITY_ID, "result": "needs-preparation",
              "toolchain": None, "rendering": None, "host_config": None,
              "consumer_observed": False, "diagnostics": [], "apply_requested": apply}
    result["scope"] = {
        "toolchain_cache": str(host_toolchain.binding_path(root).parent),
        "rendering": bool(rendering or constructs), "constructs": sorted(set(constructs)),
        "configuration": (render_host_configs.HOSTS[host]["destination"].replace("<corpus>", str(workspace))
                          if host else None),
        "staging": str(root / ".tmp" / "host-preparation") if host else None,
        "replace_host_overrides": replace_overrides,
        "projection_target": projection_target,
    }
    try:
        return _prepare_observed(root, result, apply=apply, rendering=rendering,
            constructs=constructs, host=host, workspace=workspace,
            replace_overrides=replace_overrides, projection_target=projection_target)
    except (HostEnvironmentUnavailable, OSError, ValueError, subprocess.SubprocessError) as exc:
        return preparation_failure(result, exc, capability_id=host_toolchain.CAPABILITY_ID)


def _prepare_observed(root, result, *, apply, rendering, constructs, host, workspace,
                      replace_overrides, projection_target):
    # Preview both requirements before any side effect, including invalid construct/lock inputs.
    result["stage"] = "observation"
    toolchain = prepare_host_toolchain.prepare(root, configuration=bool(host))
    render_preview = prepare_rendering_runtime.prepare_runtime(root, constructs=constructs) \
        if rendering or constructs else None
    result.update(toolchain=toolchain, rendering=render_preview)
    if not apply:
        result["result"] = "ready" if toolchain["result"] == "ready" and \
            (render_preview is None or render_preview["result"] == "ready") and host is None else "needs-preparation"
        return result
    if render_preview is not None and render_preview["result"] == "invalid":
        return result
    result["stage"] = "toolchain"
    toolchain = prepare_host_toolchain.prepare(root, apply=True, configuration=bool(host))
    result["toolchain"] = toolchain
    if toolchain["result"] != "ready":
        return result
    if rendering or constructs:
        result["stage"] = "rendering"
        result["rendering"] = None
        rendered = prepare_rendering_runtime.prepare_runtime(root, apply=True, constructs=constructs)
        result["rendering"] = rendered
        if rendered["result"] != "ready":
            return result
    if host:
        result["stage"] = "host-configuration"
        # Editing dependencies live only in the prepared interpreter. Re-enter
        # one internal mode with fixed arguments; never pip-install into this process.
        command = [toolchain["bindings"]["python"], str(root / "Tools/prepare_host.py"), str(root),
                   "--configure-only", "--apply", "--host", host, "--workspace-root", str(workspace),
                   "--projection-target", projection_target]
        if replace_overrides:
            command.append("--replace-host-overrides")
        environment = dict(os.environ, CAMBIUM_CUE=toolchain["bindings"]["cue"])
        child = kblib.run_cambium_subprocess(command, env=environment,
            capture_output=True, text=True, timeout=120)
        result["host_config"] = json.loads(child.stdout)
        if child.returncode or not result["host_config"].get("installed"):
            result["diagnostics"].append({"code": "host-installation-incomplete",
                "message": "Inspect host_config; generated, published, installed and consumer-observed are separate results"})
            return result
    result["result"] = "prepared"  # not a claim that an existing Host session has reloaded
    result["stage"] = "consumer-observation"
    result["next"] = {"tool": "inspect_host", "python": toolchain["bindings"]["python"],
                      "environment": {host_toolchain.CUE_ENV: toolchain["bindings"]["cue"]},
                      "arguments": {"root": str(workspace), "construct": list(constructs),
                                    "rendering": bool(rendering or constructs)},
                      "instruction": "Run in the actual Host consumer; reload it if explicit startup bindings changed"}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--apply", action="store_true", help="Authorize only the displayed Host preparation scope")
    parser.add_argument("--rendering", action="store_true", help="Prepare the canonical construct selector")
    parser.add_argument("--construct", action="append", default=[], help="Prepare this registered construct capability")
    parser.add_argument("--host", choices=sorted(render_host_configs.HOSTS))
    parser.add_argument("--workspace-root", type=Path, help="Corpus for the generated Host registration; defaults to root")
    parser.add_argument("--projection-target", choices=tool_availability.PROJECTION_TARGETS,
                        default=tool_availability.SOURCE_DISTRIBUTION)
    parser.add_argument("--replace-host-overrides", action="store_true",
                        help="Replace configured Python/CUE and remove explicit rendering paths to use default discovery; preserve other settings")
    parser.add_argument("--configure-only", action="store_true",
                        help="Install one Host configuration using an already prepared toolchain; never install dependencies")
    parser.add_argument("--json", action="store_true", help="Emit the same structured preparation result")
    args = parser.parse_args(argv)
    result = None
    try:
        if args.configure_only:
            if not args.host or not args.apply:
                raise ValueError("Prepared Host installation needs one host and explicit --apply")
            if args.rendering or args.construct:
                raise ValueError("Configuration-only mode cannot prepare rendering capabilities")
            toolchain = prepare_host_toolchain.prepare(args.root, configuration=True)
            if toolchain["result"] != "ready":
                raise ValueError("Prepared Host toolchain is not usable")
            result = _host_stage(args.root.resolve(), (args.workspace_root or args.root).resolve(),
                args.host, toolchain, replace_overrides=args.replace_host_overrides,
                projection_target=args.projection_target)
        else:
            result = prepare(args.root, apply=args.apply, rendering=args.rendering,
                constructs=args.construct, host=args.host, workspace=args.workspace_root,
                replace_overrides=args.replace_host_overrides, projection_target=args.projection_target)
    except (HostEnvironmentUnavailable, OSError, ValueError, subprocess.SubprocessError) as exc:
        result = {"result": "needs-preparation", "consumer_observed": False,
                  "diagnostics": [exc.diagnostic() if isinstance(exc, HostEnvironmentUnavailable)
                                  else {"code": "host-preparation-failed", "message": str(exc)}]}
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result.get("result") in ("prepared", "ready") or result.get("installed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
