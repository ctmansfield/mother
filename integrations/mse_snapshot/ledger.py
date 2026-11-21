"""Replay a snapshot only after rebuilding it from reopened authoritative state."""
from __future__ import annotations

from mse.contracts import ContractError

from .snapshot import _read_snapshot, _replay_validated_snapshot


def replay_ledger_snapshot(
    snapshot_bytes: bytes, *,
    ledger,
    expected_scope: dict,
    expected_archive_id: str,
    max_bytes: int,
    max_members: int,
) -> dict:
    """Rebuild the same request through a trusted, reopened ledger instance.

    The ledger is dependency-injected by local integration code. A client cannot
    supply an acceptance callback or a native projection through this entry point.
    """
    snapshot = _read_snapshot(snapshot_bytes, max_bytes, max_members)
    if snapshot["scope"] != expected_scope or snapshot["archive_id"] != expected_archive_id:
        raise ContractError("Snapshot does not match expected scope and archive")

    # Compare the entire immutable view, including omitted members, selection,
    # provenance and coverage. Valid membership of individual rows is insufficient.
    if ledger.verify_snapshot(snapshot) is not True:
        raise ContractError("Snapshot differs from reopened authoritative ledger")
    return _replay_validated_snapshot(snapshot_bytes, snapshot)
