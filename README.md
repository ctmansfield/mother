# MOTHER
Local, privacy-first behavioral optimization framework (Alien-verse themed).

## Physiology evidence foundation — PF-001 / 0.1.0

The 0.2.0 review increment adds an immutable local observation/revision archive,
corrected time-aware analytics, bounded source file readers, synchronized replay
for Coach and a chronological scalar baseline evaluator. Contract 1.0.0 preserves
measurement, availability, first-seen and ingestion time separately. Synthetic
verification does not establish personal performance or a deployed live system.

Start with [release notes](docs/physiology/RELEASE_NOTES.md),
[INSTALL](docs/physiology/INSTALL.md), [VERIFY](docs/physiology/VERIFY.md), and the
[dependency-aware board](docs/physiology/TASK_BOARD.md). Exact paired revisions
and patch hashes are recorded in the discrete release manifest. Use the new
offline gate: older generic verification wrappers may mask errors.

Components: Mother Core (orchestrator/event bus), models (Nostromo, Ripley, Bishop, ...), content packs, scripts.
## CI & Dev
- `make install` to set up venv and dev deps
- `make verify` to run synthetic checks
- `make test` to run pytest

## Metabolic State Engine research reference

The [MSE documentation index](docs/mse/README.md) contains the complete architecture,
repository findings, mechanistic and intervention contracts, and current integration
decisions. The executable [v0.1.0 offline prototype](research/mse/reference-v0.1.0/prototype/README.md)
is an isolated, synthetic-data research reference. It is not part of the MOTHER
service or acquisition path. See the index for verification and installation.
