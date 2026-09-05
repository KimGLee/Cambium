# Profile-bound rendering

Start from [`profiles/_template/rendering-contract.yaml`](../../../profiles/_template/rendering-contract.yaml). The common Profile slot accepts an explicit inactive answer or configured rule bindings; adopters fill this form instead of adding their own rendering sections. [`rendering-capabilities.yaml`](../../rendering-capabilities.yaml) owns supported construct/capability/acceptance bindings. The Profile selects those bindings; the Host supplies executable and dependency locations.

## Host setup

Install dependencies with `npm ci` using the exact [`static_renderer/package.json`](static_renderer/package.json) and [`package-lock.json`](static_renderer/package-lock.json). For a carried, immutable Tools distribution, copy these two files into a separate Host dependency directory and install there.

- `CAMBIUM_RENDER_NODE`: absolute Node executable path, satisfying the package engine requirement.
- `CAMBIUM_RENDER_BROWSER`: absolute Chromium-compatible browser executable path.
- `CAMBIUM_RENDER_NODE_MODULES`: the separate installation's `node_modules` directory.

The adapter verifies the package, lockfile and installed direct versions against the shipped Tool. Dependencies are not knowledge content or adopter runtime state. Render execution uses no network.

## Evidence chain

`record_profile_rendering` produces source-bound Mermaid SVG, KaTeX HTML/MathML and Markdown-table render evidence for frozen Profile obligations. The existing AuditReceipt and Batch Review consumers verify source, bindings, runtime identity, complete construct coverage and artifact integrity. Tables use the Tool's fixed static viewport and wrap-or-scroll layout; this does not claim visual acceptance for every Obsidian theme or plugin.

A missing applicable contract or unavailable compiler blocks the operation; it is not a successful check. `record_rendering_verification` remains the separate K12 verification record and cannot substitute for compilation. Authority remains with [K12/02](../../../kernel/K12%20Quality%20Assurance/02%20Rendering%20Verification.md), its [Profile shape](../../../kernel/K12%20Quality%20Assurance/profile-rendering-contract.yaml), and the referenced machine owners—not this guide.
