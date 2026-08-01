## Navigation

- Parent: [[kernel/09 Wiki Link and Navigation Standard|09 Wiki Link and Navigation Standard]].
- Previous: [[kernel/09 Wiki Link and Navigation/02 Structural and Bidirectional Links|Structural and Bidirectional Links]].
- Next: [[kernel/09 Wiki Link and Navigation/04 MOC Related and Link Creation|MOC Related and Link Creation]].

## Path And Alias Rules

- When same-named files are ambiguous, the full vault-relative path MUST be used.
- Use an alias for the display text, for example `[[kernel/00 Standards Overview|Standards Overview]]`.
- The wiki alias pipe in Markdown tables MUST be escaped: `\|`.
- After a file moves, explicit path links MUST be updated.
- Links that have only an alias without an unambiguous target MUST NOT be created.
- Domain-level references to Standards MAY point to the stable MOC; references to a specific rule, process, or gate MUST point to the canonical leaf module inside the folder.
- Task Contracts, Read Sets, and migration maps use full vault-relative module paths and MUST NOT record only a vague Standard number.

## Heading Links

When referencing a specific conclusion or process, prefer linking the heading:

```markdown
[[kernel/09 Wiki Link and Navigation/04 MOC Related and Link Creation#Link Creation Policy|Link Creation Policy]]
```

Renaming a heading breaks such links, so stable core headings SHOULD NOT be modified casually.

After a section migrates from a monolithic note to a leaf module, old heading links inside the Vault MUST be updated to the new owner; the original path-only links MAY continue to point to the stable MOC.
