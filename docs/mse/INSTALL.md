# MSE repository reference — installation, verification and rollback

These procedures use a new review directory and synthetic data. They do not
install a service or modify an existing MOTHER, COACH, Bridge or NAS data store.
Python 3.11+ and Git are required. The prototype itself uses only the Python
standard library; JSON Schema verification uses `jsonschema==4.26.0`.

## 1. Obtain the review branch

Use a new directory under the standard `/incoming` location. Git refuses to
clone into a conflicting nonempty directory. If `/incoming` is not writable,
choose another new directory you own and adjust the following paths.

```bash
git clone --branch work/mse-001-reference-and-design-20261119 \
  https://github.com/ctmansfield/mother.git /incoming/mother-mse-001-review
git -C /incoming/mother-mse-001-review rev-parse HEAD
python3 -B /incoming/mother-mse-001-review/tools/verify_mse_reference.py
```

Compare the reported Git revision with the reviewed PR head. A branch name can
move; record the selected commit with any execution result. A content hash is
an integrity check, not proof of authorship or execution authorization.

## 2. Run the complete existing verification

The following verification environment is separate from the application:

```bash
python3 -m venv /incoming/mse-001-verification-env
/incoming/mse-001-verification-env/bin/python -m pip install \
  -r /incoming/mother-mse-001-review/research/mse/verification-requirements.txt
/incoming/mse-001-verification-env/bin/python -B \
  /incoming/mother-mse-001-review/tools/verify_mse_reference.py --all
```

Expected checks: 63 payload hashes plus the original manifest; 56 prototype
tests; 25 draft-contract invariants; seven proposed SQL invariants; three exact
patch reconstructions. Verification prints failures and returns a nonzero status
when a check fails. Successful software checks do not validate metabolic
mechanisms, model calibration, causal intervention effects or real-device use.

## 3. Optional isolated prototype installation

The target must be new. The installer verifies its manifest and refuses to
overwrite an existing installation. No administrator access is required.

```bash
bash /incoming/mother-mse-001-review/research/mse/reference-v0.1.0/prototype/install.sh \
  "$HOME/mse-reference-0.1.0"
bash "$HOME/mse-reference-0.1.0/verify.sh"
```

Create a separate new data directory, then run only the supplied synthetic
example. The importer is idempotent; replay refuses to replace an existing
output file.

```bash
if mkdir -m 700 "$HOME/mse-demo-0.1.0" && cd "$HOME/mse-reference-0.1.0"; then
  if python3 -B -m mse import-healthkit examples/synthetic_healthkit_v03.json \
    --subject synthetic-person --source-instance synthetic-healthkit \
    --db "$HOME/mse-demo-0.1.0/evidence.sqlite"; then
    python3 -B -m mse replay --db "$HOME/mse-demo-0.1.0/evidence.sqlite" \
      --output "$HOME/mse-demo-0.1.0/states.json"
  fi
else
  printf '%s\n' 'A new data directory and the installed reference are required.'
fi
```

The [original validation record](../../research/mse/reference-v0.1.0/prototype/VALIDATION.md)
contains expected synthetic counts and hashes. The proposed SQL under `design/`
is not a production migration and is not the prototype's runtime schema.

## 4. Discrete patches

The original patches remain available under
`research/mse/reference-v0.1.0/patches/`:

| Patch | Preserved scope |
| --- | --- |
| P001-offline-reference.patch | Isolated reference implementation and release manifest |
| P002-research-contracts.patch | Draft research contracts, synthetic fixtures and verifier |
| P003-proposed-state-schema.patch | Proposed separate MSE database schema |

They were designed for empty review directories, not for automatic application
to an arbitrary production checkout. To inspect P001 in a new directory:

```bash
if mkdir -m 700 /incoming/mse-p001-review; then
  if git -C /incoming/mse-p001-review apply --check \
    /incoming/mother-mse-001-review/research/mse/reference-v0.1.0/patches/P001-offline-reference.patch; then
    git -C /incoming/mse-p001-review apply \
      /incoming/mother-mse-001-review/research/mse/reference-v0.1.0/patches/P001-offline-reference.patch
  fi
else
  printf '%s\n' 'Choose a new empty patch review directory.'
fi
```

## 5. Rollback and retention

For an isolated installed reference, the original retirement command verifies
the install receipt and code hashes, then renames the installation to a retained
sibling. It refuses modified or unexpected contents and deletes no files.

```bash
bash /incoming/mother-mse-001-review/research/mse/reference-v0.1.0/prototype/rollback.sh \
  "$HOME/mse-reference-0.1.0"
```

Runtime data remain in the separate data directory. Closing an unmerged review
PR leaves the saved branch and evidence intact. If a later merge must be undone,
prepare a reviewed Git revert of that exact integration commit while preserving
historical source and result records. This reference has no production service
or database rollback because it changes neither.
