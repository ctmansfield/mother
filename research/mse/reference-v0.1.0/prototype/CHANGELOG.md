# Change log — MSE-P001

All entries are new proposed implementation in an isolated prototype, not changes
to the HealthKit app or MOTHER/COACH production repositories.

| Modification | Rationale |
|---|---|
| `mse/contracts.py` | Keep observations separate from inferred states; reject unit/type/time errors and preserve explicit identities. |
| `mse/adapters.py` | Read actual v0.3 `HealthArchive` fields, honor Swift date epoch, retain opaque anchor digests and distinguish SDNN from raw intervals. |
| `mse/storage.py` | Preserve raw bytes and immutable observations in a new DB, handle duplicates/conflicts/deletions, invalidate dependent runs without erasing them. |
| `mse/model.py` | Demonstrate asynchronous scalar inference, prior-only learning, abstention and full lineage without asserting a biochemical mechanism. |
| `mse/features.py` | Make meal-area missingness explicit and distinguish signed from positive incremental area. |
| `mse/__init__.py` | Pin package/model versions and exact executable source digest. |
| `mse/__main__.py` | Expose offline imports and replay with explicit paths and refusal to overwrite derived output files. |
| `pyproject.toml` | Describe the optional Python package; normal installation uses no dependency downloads. |
| `tools/lifecycle.py`, shell wrappers | Provide manifest-verified additive installation, verification and non-deleting retirement. |
| `tools/make_synthetic_example.py`, `examples/` | Reproduce public synthetic observations and an auditable reference output. |
| `tests/` | Exercise errors, time and identity semantics, source isolation, missingness, lineage, deterministic replay and lifecycle safeguards. |
| Documentation and manifest | Record exact scope, commands, observed verification, numerical assumptions and remaining scientific gates. |

During implementation, review found two lineage/independence risks before release:
earlier baseline dependencies could fall out of a moving window while still
contributing to the OU posterior, and simultaneous outputs could inflate the
baseline count. The final implementation carries recursive observation ancestry
and uses one stable representative per timestamp per model group. Regression
tests cover both. No failed software test was relabeled as successful.

## Independent-review corrections before release

The independent reviewer subsequently demonstrated three additional gaps. The
earlier 43-test pass did not cover them and is not evidence that they were absent.

| Finding | Correction and rationale |
|---|---|
| A prior start could precede the target while the aggregate interval ended later. | Index reference estimates by interval end; baseline supports must be complete and nonoverlapping. Overlapping and same-time samples abstain. |
| A global receipt filter could be mistaken for historical as-available replay. | Restrict the executable contract to `retrospective_snapshot`; emit explicit false historical-availability fields and latest supporting receipt; reject source-as-available/online modes. |
| Method and acquisition-window changes could pool. | Stratify by method, exact recorded interval duration, declared window and calibration identity in addition to the existing source/context dimensions. |
| Known motion artifact could contribute while its flag disappeared from state summaries. | Exclude exact known-invalid flags from baseline/filter; invalid current readings produce unknown; propagate current, baseline, recursive-ancestor, support and exclusion quality summaries. |

Added thirteen targeted regression tests for the reproduced probes, overlapping
intervals, aggregate end timestamps, receipt cutoff semantics, mode refusal,
method/window/calibration changes, invalid current measurements and recursive
quality lineage. Documentation now uses exact `unknown` /
`insufficient_prior_baseline` status values and does not call the retrospective
snapshot a per-target historical knowledge set.
