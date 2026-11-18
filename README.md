# MOTHER
Local, privacy-first behavioral optimization framework (Alien-verse themed).

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
