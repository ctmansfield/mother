# Offline selected HealthKit archive candidate

The selected archive implements the [ATLAS 0.1 contract](../../docs/mse/integration/selected-healthkit/CONTRACT.md) at commit `35ec23899e36d81d9d3afdbbc7cee9034313da4e`. `SelectedArchive.batch_request` exercises the v2 PUT and GET contract in process. The deployed TLS entry point exposes only its existing v1 synthetic 0.2 API. The selected implementation has no listener or live-data configuration.

## Storage and access

Allocate a separate canonical 0700 root owned by the test process, with an empty directory for initialization. Supply the synthetic scope and archive identity from the trusted fixture grant and provide an allowlist of exact synthetic body digests. Initialization refuses nonempty roots, including an existing v1 archive. Reopen through the same identity without initializing. There is no migration of v1 stores and no write to them. The candidate uses a single SQLite transaction for each exact original, receipt and linked processing evidence. Reopen verifies the original, receipt binding and every accepted sighting before returning a terminal receipt. Read-only paths use SQLite read-only mode.

The adapter accepts the 12 selected quantity types, sleep categories and workout summaries, and typed deletions. It retains decimal text, all source intervals, nullable source references and workout totals, and each sighting’s collector receipt time. An oxygen fraction outside the processing domain is retained with an explicit finding. A changed source fact under the same metric, UUID and operation quarantines the whole batch and retains its original. Retry of identical bytes returns the same receipt. Different bytes under an already bound batch conflict. A tombstone excludes that key from the current view starting at its commit cutoff, including unknown-key deletes and a later upsert under a deleted key. A source replacement with a new UUID is independent. There is no automatic age purge or aggregation across overlapping sources.

## Export

`export(start, through)` returns a canonical JSON envelope with the exact view digest and each accepted sighting’s original record, source fact digest, processing digest and receipt. Read a quarantine receipt and original by its batch ID. The view is scoped to the archive and streams no unselected fields. With `current=True`, the export uses the supplied `through` as the cutoff and selects first sightings within the interval, with tombstones considered through that cutoff. It refuses ranges over eight commit positions. A future multi-page API needs separate scan and snapshot cutoffs. Optional `event_window` filters upserts by half-open event overlap and preserves interval bounds. Tombstones have no event interval and appear in unfiltered history.

Selected collection and deletion never erase already archived data. Retention, erasure policy, route activation, real grant custody, and backup/restore are separate follow-on decisions. No PF-001 processing run ID is invented for this contract.

From the repository root, run the selected and legacy source tests with the archive requirements installed.

```sh
python -B -m unittest discover -s tests/integration/mse_archive_service -v
```
