# Restricted analytical lineage resolver

This local prototype follows the provisional ATLAS privacy interface at `794591cfddbd05a2b226f917679429b104bbbac8` and builds on accepted synthetic custody [#35](https://github.com/ctmansfield/mother/commit/b7aae4f2216d27f0544eab9fe9698286fe49d716).

The trusted bootstrap supplies the FORGE custody service, expected archive and private registry directory. FORGE issues the random external `view_id` and checks credentials and current generation independently of this restorable mapping. ORACLE serves the allowlisted analytical bytes through its authorized path. Projection writers bind the exact verified input and output bytes once. Binding returns no public lineage payload. Only a separate current audit credential resolves the private mapping. Exact replay rechecks the snapshot against the actual reopened ledger and compares the complete saved MSE manifest. Authorization is checked again before returning the restricted result.

The registry persists scope, purpose, recipient, policy, generation, expiry, archive and exact byte hashes in a private SQLite mapping. It accepts no supplied identity or role as authority. All path, parser and replay denials use the same outward text. Correction, expiry and revocation are controlled by FORGE's current authority. An old mapping cannot override it. A shared filesystem identity, full host compromise or a coordinated rollback of the authoritative generation store remains outside this prototype.

From a dependency-enabled checkout of the exact accepted baseline and this change:

```sh
PYTHONPATH=.:research/mse/reference-v0.1.0/prototype python -B -m unittest discover -s tests/integration/mse_privacy/lineage -v
```

The focused tests use real public capture ingestion, a reopened PF-001 ledger and exact MSE replay. A scoped fixture models the independently updated authority when run without the FORGE privacy candidate. Combined acceptance must use FORGE's actual privacy authority, ORACLE's projection writer and an independent stale-restore test.
