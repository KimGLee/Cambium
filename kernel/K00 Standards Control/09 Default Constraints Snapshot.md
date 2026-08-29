## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]].
- Next: [[kernel/K00 Standards Control/11 Standards Map and Rule Registry|Standards Map and Rule Registry]].

## Purpose

This module is a navigation view of standing defaults. It owns no duplicated rule text and cannot override the canonical leaf that defines a default's meaning. Conflicts are resolved by [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract#Standard Precedence|Standard Precedence]].

## Default Owner Index

The `execution-defaults-base` machine registry is the unique authority for default membership, value, unit, range, and whether Profile binding is allowed. Each registry entry points to the Kernel leaf that owns the item's meaning. Markdown summaries, Cards, Profile forms, and runtime state may reference or project that registry but MUST NOT maintain another complete default list.

## Related

- [[kernel/K00 Standards Overview|Standards Overview]]
- [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]]
- [[kernel/K00 Standards Control/05 Core Principles|Core Principles]]
