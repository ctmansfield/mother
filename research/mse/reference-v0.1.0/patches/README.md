# Discrete, standalone add-only patches

These patches make each new deliverable reviewable as a diff. They have no
upstream repository base and are intended only for a new, empty review directory.
They do not change an existing MOTHER, COACH or Health Bridge file. The unpacked
bundle already contains all corresponding files, so applying patches is optional.

| Patch | New files and effect |
|---|---|
| `P001-offline-reference.patch` | Adds `mse-reference/` with the final 22-file prototype payload and its release manifest |
| `P002-research-contracts.patch` | Adds `mse-design/contracts/` with draft JSON Schemas, synthetic examples, typed-condition validator and documentation |
| `P003-proposed-state-schema.patch` | Adds `mse-design/001_mse_proposed.sql`; a future separate database proposal, never an automatic migration |

Each patch was checked with `git apply --check`, applied in a distinct empty
temporary directory and compared byte-for-byte by file hashes with the source
deliverable. See `../verification/PATCH_VERIFICATION.json`.

An optional check, after creating and entering an empty directory, is:

```bash
git apply --check /incoming/mse-001-0.1.0-review/mse-review-v0.1.0/patches/P001-offline-reference.patch
```

Use the normal installer in `../INSTALL.md` to run the prototype. Before any
future upstream integration, choose the reviewed repository base, map its source
contracts and rerun its existing tests in an isolated worktree. These standalone
patches do not resolve upstream packaging or merge decisions.
