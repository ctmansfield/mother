# MSE-001 v0.1.0 - isolated installation and verification

This package is a review bundle. It does not patch an existing repository, install
a service, select a production database, change signing or alter credentials.
The embedded prototype requires Python 3.11+ and the standard library only.

## 1. Download and verify

Place `mother-coach-mse-0.1.0.tgz` in your standard `/incoming` directory. Compare
its SHA-256 to the value in the delivery response or accompanying checksum file:

```bash
sha256sum /incoming/mother-coach-mse-0.1.0.tgz
```

On macOS the equivalent is `shasum -a 256 FILE`. A checksum detects changed bytes;
it does not independently authenticate the author.

## 2. Extract into a new review directory

This example assumes `/incoming` is writable by your current user. It refuses
to reuse a previously existing review directory. No command closes your shell.

```bash
if mkdir -m 700 /incoming/mse-001-0.1.0-review; then
  tar --keep-old-files -xzf /incoming/mother-coach-mse-0.1.0.tgz \
    -C /incoming/mse-001-0.1.0-review
else
  printf '%s\n' 'Review directory exists or could not be created; choose a new directory.'
fi
```

The archive contains `mse-review-v0.1.0/`. Read the report, release notes and
prototype README before choosing real inputs. All shipped measurements are
synthetic. The design SQL is a proposal for a separate future database, not an
installer migration and not the prototype's runtime schema.

## 3. Install the prototype into a new directory

```bash
if bash /incoming/mse-001-0.1.0-review/mse-review-v0.1.0/prototype/install.sh \
  "$HOME/mse-reference-0.1.0"; then
  bash "$HOME/mse-reference-0.1.0/verify.sh"
else
  printf '%s\n' 'Installation did not complete; inspect the error before continuing.'
fi
```

The target must not exist. The installer verifies the release manifest and copies
only its listed files. It downloads no dependencies. Verification operates on
synthetic data and unique temporary directories. Keep runtime data outside the
installed code directory so ownership checks can verify retirement safely.

## 4. Run the synthetic vertical slice

Choose a new output directory. The import is idempotent; replay refuses to
overwrite an existing JSON output. These commands are for synthetic input only.

```bash
if mkdir -m 700 "$HOME/mse-demo-0.1.0" && cd "$HOME/mse-reference-0.1.0"; then
  if python3 -B -m mse import-healthkit examples/synthetic_healthkit_v03.json \
    --subject synthetic-person --source-instance synthetic-healthkit \
    --db "$HOME/mse-demo-0.1.0/evidence.sqlite"; then
    python3 -B -m mse replay --db "$HOME/mse-demo-0.1.0/evidence.sqlite" \
      --output "$HOME/mse-demo-0.1.0/states.json"
  fi
else
  printf '%s\n' 'A new output directory and the installed package are required; inspect the error.'
fi
```

Expected counts and exact fingerprints are in `prototype/VALIDATION.md` and
`verification/VERIFICATION.md`. The 26 synthetic records yield both abstentions
and model-conditioned estimates. No physiological mechanism is declared known.
The optional receipt cutoff is a retrospective snapshot filter, not a proven
historical MOTHER-availability reconstruction.

## 5. Verify draft design contracts (optional)

These design checks require the existing Python packages `jsonschema` and
`referencing`; they are not runtime dependencies of the prototype. No installer
automatically adds them. In an environment that already has them:

```bash
python3 /incoming/mse-001-0.1.0-review/mse-review-v0.1.0/design/contracts/validate_contracts.py
python3 /incoming/mse-001-0.1.0-review/mse-review-v0.1.0/verification/verify_design_sql.py
```

The latter uses an in-memory SQLite database only. Neither command touches a
production database or source archive.

## 6. Rollback / retirement

```bash
bash "$HOME/mse-reference-0.1.0/rollback.sh" "$HOME/mse-reference-0.1.0"
```

This verifies the receipt and manifest and renames the entire unchanged code
installation to a sibling `*.retired-<timestamp>-<id>` directory. Nothing is
deleted. Modified/untracked content causes refusal and remains intact. External
runtime data and original input copies are retained. To restore, rename the
reported retired directory to the original path only when that path is absent.
No production-service rollback exists because no production service was changed.

## 7. Future repository integration

The release intentionally contains no patch against an uncertain MOTHER feature
base. Select the reviewed PF001/I01 integration commit and authoritative export
contract first. Then add the package under a new `mother/mse/` boundary, reconcile
packaging and run the existing physiology contracts plus MSE tests in an isolated
worktree. Commit only reviewed explicit paths. No push, merge or deployment is
part of this release.
