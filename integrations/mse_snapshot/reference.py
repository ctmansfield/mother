"""Execute a synthetic snapshot projection through the preserved MSE reference."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from mse import implementation_sha256
from mse.adapters import native_replay
from mse.contracts import ContractError, digest
from mse.model import replay
from mse.storage import Store

REFERENCE_CODE_SHA256 = "998ad8654a801945bd0fa10b93de75755bee929317b49b3701584372e0e7dbf1"
BRIDGE_VERSION = "mse-snapshot-reference/0.1"


def _replay_projection(snapshot_bytes: bytes, projection_bytes: bytes) -> dict:
    """Internal runner. A snapshot mapper must construct and validate the projection."""
    if implementation_sha256() != REFERENCE_CODE_SHA256:
        raise ContractError("Unexpected MSE reference implementation")

    observations, tombstones, metadata = native_replay(projection_bytes)
    if not metadata["synthetic"]:
        raise ContractError("The offline bridge requires an explicit synthetic projection")
    observation_ids = {record["observation_id"] for record in observations}
    if len(observation_ids) != len(observations):
        raise ContractError("Projection must select one revision per observation")

    snapshot_sha256 = sha256(snapshot_bytes).hexdigest()
    with TemporaryDirectory(prefix="mse-synthetic-") as scratch:
        with Store(Path(scratch) / "reference.sqlite") as store:
            receipt = store.import_batch(
                projection_bytes, observations, tombstones, metadata
            )
            # The snapshot mapper already selects as-of revisions. The reference's
            # optional receipt cutoff uses different clocks and must stay unset.
            run = replay(store)

    lineage = {
        "snapshot_sha256": snapshot_sha256,
        "projection_sha256": receipt["artifact_sha256"],
        "adapter_version": BRIDGE_VERSION,
        "adapter_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "reference_adapter_version": metadata["adapter_version"],
        "reference_implementation_sha256": run["implementation_sha256"],
        "model_version": run["model_version"],
        "model_config_sha256": run["config_hash"],
        "reference_run_id": run["run_id"],
        "reference_result_sha256": digest(run),
    }
    return {
        "epistemic_class": "derived",
        "result_id": "derived:" + digest(lineage),
        "status": "completed" if run["active_observation_count"] else "unavailable",
        "unavailable_reason": (
            None if run["active_observation_count"] else "no_active_observations"
        ),
        "lineage": lineage,
        "reference_result": run,
    }
