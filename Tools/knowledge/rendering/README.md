# Profile-bound rendering

The [Profile interview workflow](../../../profiles/README.md) creates a candidate from the sole [`profiles/_template/`](../../../profiles/_template/) entry and records confirmed answers in `profile.toml`. Its rendering slot accepts an explicit inactive answer or configured rule bindings; do not add standalone rendering sections or Host installation paths to the Profile. [`rendering-capabilities.yaml`](../../rendering-capabilities.yaml) owns supported construct/capability/acceptance bindings. The Profile selects those bindings; Tool and Host handle executable and dependency readiness.

## Host setup

First use goes through [`prepare_host`](../../prepare_host.py), which also prepares the Profile toolchain and Host connection. `prepare_rendering_runtime` remains its narrow rendering provider and can be called independently. Default invocation is read-only; explicit `--apply` performs the reported preparation in Host-owned storage, within the user's installation authorization. Missing software or denied installation remains a Host boundary; setup does not approve Profile policy, create a Gate result, or open a batch.

```text
python3 Tools/prepare_rendering_runtime.py . --json
python3 Tools/prepare_rendering_runtime.py . --apply --json
```

With no construct request the self-test proves AST selection only. Add `--construct dollar-math` to actually compile the synthetic formula; use `--construct mermaid-fence` for SVG compilation or `--construct outer-pipe-markdown-table` for reference layout. The capability registry determines the dependencies; callers do not choose a browser switch. Source selection and KaTeX HTML/MathML compilation do not probe or execute a browser. Runner requests the capability needed at its current action boundary; inspecting `next_action` never installs dependencies.

Dependency versions and Node engine requirements come from the existing [`static_renderer/package.json`](static_renderer/package.json) and [`package-lock.json`](static_renderer/package-lock.json), not a second setup version list. The Agent reuses compatible Node and the prepared lock-specific Host dependency directory. When needed, preparation installs the locked Playwright package's Chromium into an isolated Host cache and smoke-tests it headlessly. It does not discover or default to the user's daily Chrome; an explicit Host executable override remains possible. Readiness is verified by execution, not merely by a successful install command.

The preparation result identifies the generated Host bindings file. CLI and MCP subprocesses can consume the matching default Host binding. To include it explicitly in Host products, the Agent passes that returned absolute path to `render_host_configs --runtime-bindings`, using the existing bound roots and separate Host staging directory. The generator validates the prepared input and renders reproducible products; it does not discover or install dependencies. Repeat the same invocation with `--check` to verify it. Omitting `--runtime-bindings` leaves source-distribution templates independent of the local machine.

The validated map supplies `CAMBIUM_RENDER_NODE`, optional `CAMBIUM_RENDER_BROWSER`, and `CAMBIUM_RENDER_NODE_MODULES`. Users do not need to discover or maintain these paths. A different computer prepares its own bindings. Installation files and bindings are neither Profile policy nor `.cambium` state. The adapter revalidates executables, package, lockfile and installed direct versions against the shipped Tool. Render execution uses no network.

## Evidence chain

`record_profile_rendering` produces source-bound Mermaid SVG, KaTeX HTML/MathML and Markdown-table render evidence for frozen Profile obligations. Each obligation covers only its registered construct and binds only the executables it uses. Repeating `--obligation-id` shares source parsing, a Node process and (where required) a browser across the read-only group; the original producer still publishes separate plan-bound records under its writer lock. AuditReceipt and Batch Review consumers verify those same source, binding, runtime, coverage and artifact contracts.

Mermaid compilation uses Chromium internally and retains the SVG geometry check. KaTeX produces HTML/MathML directly in Node, without adding a layout requirement. Tables retain the fixed reference viewport, font and wrap-or-scroll checks. This is not a claim about every Obsidian theme, plugin or final Host UI. Parser, compiler and layout are selectable implementation capabilities, not new Kernel levels or mandatory successive stages.

A missing applicable contract or unavailable compiler blocks the operation; it is not a successful check. `record_rendering_verification` remains the separate K12 verification record and cannot substitute for compilation. Authority remains with [K12/02](../../../kernel/K12%20Quality%20Assurance/02%20Rendering%20Verification.md), its [Profile shape](../../../kernel/K12%20Quality%20Assurance/profile-rendering-contract.yaml), and the referenced machine owners—not this guide.
