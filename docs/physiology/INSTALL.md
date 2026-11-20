# INSTALL — PF-001 / 0.1.0

This increment prepares isolated Coach and Mother review trees. It does not
replace a running checkout, start services, configure a device, change
credentials, or migrate the existing application PostgreSQL database. Exact
compatible revisions, tree IDs and patch hashes are in the bundle's
`manifest.json`. Application package version: Mother 0.2.0; contract: 1.0.0.

## Prerequisites and paths

Use Git and Python 3.12 on a local filesystem. Python 3.12.14 and Git 2.51.1 were
used for release verification. The supplied dependency pins reproduce that
verification environment. Node 24.22.1 was used to execute the Node-RED function
fixtures. Docker, Home Assistant, Node-RED, Nightscout and a live database are
not needed for the offline release gate.

Save and extract the discrete bundle in a new directory, for example beneath
`/mnt/nas_storage/incoming/`. Treat that path as a suggested drop location; the
active NAS/VM layout has not been verified. The installer takes explicit paths
to the user's existing Git repositories and creates new worktrees from the
pinned review bases. Existing branches may be ahead or dirty; their contents
are preserved. Changes after the review bases are not silently incorporated.
Integration with those changes is a subsequent reviewed merge.

From the extracted bundle directory, replacing the three paths as needed:

```bash
python3 install.py \
  --mother-repo /path/to/existing/mother \
  --coach-repo /path/to/existing/coach \
  --destination /path/to/new/pf001-review
```

The base commits must exist in the repositories. The installer verifies patch
checksums before mutation, suppresses Git hooks for its commands, checks patch
application, and compares both resulting Git trees with the release manifest.
It verifies HEAD, staged entries and tracked/nonignored-untracked contents of
the reference checkouts before and after installation. Ignored files are not
included in that content comparison. It creates Git worktree/branch metadata,
but does not modify the reference checkout's files or commit its index.

`install_state.json` records the new worktrees, reviewed commits and expected
trees. The patches remain staged in the review trees so they can be inspected.
If installation fails, it returns nonzero and leaves partial worktrees plus a
failure record for inspection. It does not reset or delete work to recover.

## Create a separate verification environment

Keep the environment outside both review worktrees. The verifier requires exact
release contents and rejects untracked/ignored files that could alter imports.

```bash
python3 -m venv /path/to/pf001-venv
/path/to/pf001-venv/bin/python -m pip install -r requirements-verify.txt
python3 verify.py \
  --installation /path/to/new/pf001-review \
  --python /path/to/pf001-venv/bin/python
```

Dependency installation may access the package index. The subsequent tests and
synthetic replay operate offline. Inspect each command's exit result; the
Python entry points and shell wrappers propagate failures. No shell strict-mode
or terminal-closing snippet is required. See `VERIFY.md` for acceptance details.

## Use the additive archive after source qualification

The canonical archive is an explicit SQLite path, separate from old Parquet
views and application databases. Opening a new archive initializes migration
`0001_archive.sql` transactionally. Original files and source revisions remain
immutable; processing changes create separately versioned normalized records.
Put the archive on storage whose locking and durability have been qualified.
The user's NAS filesystem has not been qualified for SQLite by this release.

The offline demo exercises all available file adapters:

```bash
cd /path/to/new/pf001-review/mother
/path/to/pf001-venv/bin/python -m mother.physiology.cli demo \
  --output-dir /path/to/new/synthetic-demo
cd /path/to/new/pf001-review/coach
/path/to/pf001-venv/bin/python -m coach_app.physiology.replay \
  --input /path/to/new/synthetic-demo/synthetic_replay.json \
  --output /path/to/new/synthetic-demo/synthetic_replay.html
```

For a qualified Apple Health XML file, use a stable subject and source namespace:

```bash
cd /path/to/new/pf001-review/mother
/path/to/pf001-venv/bin/python -m mother.physiology.cli import \
  --archive /path/to/local/physiology.sqlite3 \
  --source /path/to/export.xml --format apple_xml \
  --source-instance watch-export-source-1 --subject self
```

The other implemented formats are `polar_tcx` and the defined `spot_csv` format
in `CAPABILITIES.md`. These are bounded first readers, with a 128 MiB input limit.
Do not assume an arbitrary vendor export or a complete years-long Apple export
will fit that boundary. A larger-file reader is a separate data-qualification
task; retain the original file before any extraction.

For an offline Nightscout entries JSON response:

```bash
/path/to/pf001-venv/bin/python -m analytics.preprocess.sources.nightscout_adapter \
  --input-json /path/to/nightscout-entries.json --collection entries \
  --source-instance nightscout-local-1 --subject-id self \
  --archive /path/to/local/physiology.sqlite3 \
  --analytics-dir /path/to/new/derived-analytics
```

Do not use the existing `storage/analytics` directory for this first import.
The adapter refuses to overwrite existing unarchived Parquet history. An import
can be durably completed before this projection guard refuses view generation;
inspect its manifest and rerun the projection into a new directory. Do not
delete old files to evade provenance reconciliation.

## Upgrade and rollback implications

No existing PostgreSQL migration, deployed flow import, cron change, service
restart, host mount change or password change is included. Legacy analytics
windows and discovery outputs must be regenerated from qualified archived
inputs because target construction changed. Old precision values remain
discovery statistics, not independent forecast evidence.

Rollback of this review installation is simply to stop using its isolated
worktrees. Preserve the new archive and original artifacts; reverting software
does not justify deleting evidence. Remove a review worktree only after checking
for subsequent user work, using normal Git worktree management. Production
upgrade/rollback instructions require the actual deployed revision, launch
family, storage path, backup and restart evidence first.
