# Profile-bound rendering

The [Profile interview workflow](../../../profiles/README.md) creates a candidate from the sole [`profiles/_template/`](../../../profiles/_template/) entry and records confirmed answers in `profile.toml`. Its rendering slot accepts an explicit inactive answer or configured rule bindings; do not add standalone rendering sections or Host installation paths to the Profile. [`rendering-capabilities.yaml`](../../rendering-capabilities.yaml) owns supported construct/capability/acceptance bindings. The Profile selects those bindings; Tool and Host handle executable and dependency readiness.

## Host setup

The Agent calls `prepare_rendering_runtime` before operations that require the parser or renderer. Its default invocation is read-only: discover available executables and validate installed dependencies. An explicit `--apply` performs the reported preparation in Host-owned storage, within the user's installation authorization. Missing software or denied installation remains a Host boundary; setup does not approve Profile policy, create a Gate result, or open a batch.

```text
python3 Tools/prepare_rendering_runtime.py . --json
python3 Tools/prepare_rendering_runtime.py . --apply --json
```

Add `--require-browser` to inspect or prepare actual rendering, rather than parser-only readiness. Runner requests the capability needed at its current action boundary; inspecting `next_action` never installs dependencies.

Dependency versions and Node engine requirements come from the existing [`static_renderer/package.json`](static_renderer/package.json) and [`package-lock.json`](static_renderer/package-lock.json), not a second setup version list. The Agent reuses compatible local programs and the prepared lock-specific Host dependency directory. A browser is required for rendering, not for the parser-only stage. Readiness is verified by execution, not merely by a successful install command.

The preparation result identifies the generated Host bindings file. CLI and MCP subprocesses can consume the matching default Host binding. To include it explicitly in Host products, the Agent passes that returned absolute path to `render_host_configs --runtime-bindings`, using the existing bound roots and separate Host staging directory. The generator validates the prepared input and renders reproducible products; it does not discover or install dependencies. Repeat the same invocation with `--check` to verify it. Omitting `--runtime-bindings` leaves source-distribution templates independent of the local machine.

The validated map supplies `CAMBIUM_RENDER_NODE`, optional `CAMBIUM_RENDER_BROWSER`, and `CAMBIUM_RENDER_NODE_MODULES`. Users do not need to discover or maintain these paths. A different computer prepares its own bindings. Installation files and bindings are neither Profile policy nor `.cambium` state. The adapter revalidates executables, package, lockfile and installed direct versions against the shipped Tool. Render execution uses no network.

## Evidence chain

`record_profile_rendering` produces source-bound Mermaid SVG, KaTeX HTML/MathML and Markdown-table render evidence for frozen Profile obligations. The existing AuditReceipt and Batch Review consumers verify source, bindings, runtime identity, complete construct coverage and artifact integrity. Tables use the Tool's fixed static viewport and wrap-or-scroll layout; this does not claim visual acceptance for every Obsidian theme or plugin.

A missing applicable contract or unavailable compiler blocks the operation; it is not a successful check. `record_rendering_verification` remains the separate K12 verification record and cannot substitute for compilation. Authority remains with [K12/02](../../../kernel/K12%20Quality%20Assurance/02%20Rendering%20Verification.md), its [Profile shape](../../../kernel/K12%20Quality%20Assurance/profile-rendering-contract.yaml), and the referenced machine owners—not this guide.
