"""Observe what this CLI/MCP consumer can actually use; never install or adopt."""

import argparse
import json
from pathlib import Path
import sys

from Tools.platform.common import host_toolchain
from Tools.platform.common.host_environment import HostEnvironmentUnavailable
from Tools.knowledge.rendering import static_render_runtime


def observe(root, *, constructs=(), rendering=False):
    distribution = Path(__file__).resolve().parents[3]
    result = {"workspace": str(Path(root).resolve()), "distribution": str(distribution),
              "process_python": sys.executable, "toolchain": host_toolchain.observe(distribution, current_process=True),
              "rendering": None, "receipt_verdict": None, "installed_by_this_call": False}
    if constructs or rendering:
        request = static_render_runtime.rendering_request(distribution, constructs)
        result["rendering"] = dict(static_render_runtime.probe_runtime(distribution,
            require_browser=request["requires_browser"]), request=request)
    parts = [result["toolchain"]] + ([result["rendering"]] if result["rendering"] else [])
    result["result"] = "available" if all(part["result"] == "ready" for part in parts) else "await-host"
    result["proof_scope"] = "Current process dependency observation; not synthetic compilation or page evidence"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--construct", action="append", default=[])
    parser.add_argument("--rendering", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = observe(args.root, constructs=args.construct, rendering=args.rendering)
    except (OSError, ValueError, HostEnvironmentUnavailable) as exc:
        result = {"result": "await-host" if isinstance(exc, HostEnvironmentUnavailable) else "invalid",
                  "diagnostics": [exc.diagnostic() if isinstance(exc, HostEnvironmentUnavailable)
                                  else {"message": str(exc)}]}
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["result"] == "available" else 1


if __name__ == "__main__":
    raise SystemExit(main())
