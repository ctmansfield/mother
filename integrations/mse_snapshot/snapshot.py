"""Project the candidate ATLAS 0.2 snapshot contract into native MSE replay."""
from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from hashlib import sha256
from pathlib import Path
import re
from uuid import UUID

from mse.contracts import ContractError, SWIFT_EPOCH, canonical, digest, identifier, read_json, timestamp, utc

from .reference import _replay_projection

SNAPSHOT_VERSION = "mse.evidence-snapshot/0.2"
MAPPING_VERSION = "mse-snapshot-provisional/0.2"
SAFE_INTEGER = 2**53 - 1
TOP_FIELDS = set("""
    schema_version scope archive_id purpose measurement_start measurement_end
    knowledge_cutoff_sequence normalizer_version coverage observations tombstones
    losses snapshot_sha256
""".split())
SCOPE_FIELDS = {"subject_id", "source_system", "source_instance", "collection"}
COMMIT_FIELDS = {"artifact_sha256", "receipt_id", "mother_received_at", "committed_at", "commit_sequence"}
OBSERVATION_FIELDS = set("""
    channel original_value original_unit value unit original_start original_end
    original_received_at event_start event_end collector_received_at source_name
    bundle_id epistemic_type classification_basis classification_evidence_sha256
    device_id calibration_id source_available_at
""".split())
PROCESSING_FIELDS = set("""
    channel value unit event_start event_end epistemic_type classification_basis
    classification_evidence_sha256
""".split())
CLASSIFICATIONS = {
    ("heart_rate", "bpm", "unknown"): "capture_derivation_unavailable",
    ("heart_rate", "bpm", "measured"): "independent_measured_evidence",
    ("hrv_sdnn", "ms", "vendor_derived"): "healthkit_sdnn",
}


def _fields(value, expected):
    if not isinstance(value, dict) or set(value) != expected:
        raise ContractError("Unexpected snapshot fields")


def _match(value, pattern):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ContractError("Invalid snapshot scalar encoding")


def _clock(value):
    try:
        parsed = timestamp(value)
        if value == utc(parsed):
            return parsed
    except (OverflowError, ValueError):
        pass
    raise ContractError("Expected canonical UTC timestamp")


def _decimal(token):
    _match(token, r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
    try:
        number = Decimal(token)
    except InvalidOperation as exc:
        raise ContractError("Invalid decimal token") from exc
    if abs(number.adjusted()) > 308 or abs(number.as_tuple().exponent) > 1024:
        raise ContractError("Decimal exceeds bridge numeric range")
    fixed = format(number, "f")
    if not number:
        return "0"
    return fixed.rstrip("0").rstrip(".") if "." in fixed else fixed


def _date(token):
    number = Decimal(_decimal(token))
    try:
        with localcontext() as ctx:
            ctx.prec = max(28, len(number.as_tuple().digits) + 6)
            micros = (number * 1_000_000).to_integral_value(rounding=ROUND_HALF_EVEN)
        return utc(SWIFT_EPOCH + timedelta(microseconds=int(micros)))
    except OverflowError as exc:
        raise ContractError("Swift clock outside supported range") from exc


def _check_json(value):
    if isinstance(value, float) or (type(value) is int and abs(value) > SAFE_INTEGER):
        raise ContractError("Unsupported shared JSON number")
    if isinstance(value, str):
        value.encode("utf-8")
    if isinstance(value, dict):
        for key, item in value.items():
            _check_json(key)
            _check_json(item)
    if isinstance(value, list):
        for item in value:
            _check_json(item)


def _token(value):
    _match(value, r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


def _sha(value):
    _match(value, r"[0-9a-f]{64}")


def _read_snapshot(snapshot_bytes, max_bytes, max_members):
    if any(type(n) is not int or n <= 0 for n in (max_bytes, max_members)):
        raise ContractError("Snapshot limits must be positive integers")
    if len(snapshot_bytes) > max_bytes:
        raise ContractError("Snapshot exceeds byte limit")
    try:
        snapshot = read_json(snapshot_bytes.decode("utf-8"))
        _check_json(snapshot)
        _fields(snapshot, TOP_FIELDS)
        _sha(snapshot["snapshot_sha256"])
        preimage = {k: v for k, v in snapshot.items() if k != "snapshot_sha256"}
        if digest(["mse.snapshot/0.2", preimage]) != snapshot["snapshot_sha256"]:
            raise ContractError("Snapshot digest mismatch")
    except (UnicodeError, RecursionError) as exc:
        raise ContractError("Invalid snapshot encoding") from exc
    if (snapshot["schema_version"], snapshot["purpose"]) != (SNAPSHOT_VERSION, "offline_synthetic_replay"):
        raise ContractError("Unsupported snapshot version or purpose")
    scope = snapshot["scope"]
    _fields(scope, SCOPE_FIELDS)
    if (scope["source_system"], scope["collection"]) != ("healthkit", "healtharchive"):
        raise ContractError("Unsupported snapshot source scope")
    for value in (scope["subject_id"], scope["source_instance"], snapshot["archive_id"], snapshot["normalizer_version"]):
        _token(value)
    if any(not isinstance(snapshot[k], list) for k in ("observations", "tombstones", "losses")):
        raise ContractError("Invalid snapshot arrays")
    if sum(len(snapshot[k]) for k in ("observations", "tombstones", "losses")) > max_members:
        raise ContractError("Snapshot exceeds member limit")

    coverage = snapshot["coverage"]
    clock_fields = {"backfill_start", "observed_start", "observed_end"}
    _fields(coverage, clock_fields | {"capture_kind", "permissions", "completeness"})
    if coverage["capture_kind"] not in ("full_file", "partial") or any(
        coverage[k] != "unknown" for k in ("permissions", "completeness")
    ):
        raise ContractError("Unsupported coverage assertion")
    for key in clock_fields:
        if coverage[key] is not None:
            _clock(coverage[key])
    for loss in snapshot["losses"]:
        _fields(loss, {"field", "reason", "locator"})
        if not isinstance(loss["field"], str) or not loss["field"]:
            raise ContractError("Missing loss field")
        _token(loss["reason"])
        if loss["locator"] is not None:
            _match(loss["locator"], r"/(?:[^~]|~[01])*")
    loss_encodings = [canonical(loss) for loss in snapshot["losses"]]
    if loss_encodings != sorted(set(loss_encodings)):
        raise ContractError("Unordered or repeated losses")
    return snapshot


def _member(member, operation, snapshot):
    observation = operation == "upsert"
    extras = {"processing_revision_sha256"} if observation else set()
    _fields(member, COMMIT_FIELDS | {"pf001_revision_id", "source_revision"} | extras)
    for key in ("artifact_sha256", "receipt_id"):
        _sha(member[key])
    _match(member["pf001_revision_id"], r"[\s\S]+")
    sequence = member["commit_sequence"]
    if type(sequence) is not int or not 1 <= sequence <= snapshot["knowledge_cutoff_sequence"]:
        raise ContractError("Snapshot member outside commitment cutoff")
    if _clock(member["committed_at"]) < _clock(member["mother_received_at"]):
        raise ContractError("Commitment precedes MOTHER receipt")

    revision = member["source_revision"]
    payload_fields = {"observation"} if observation else {"deleted_at", "original_deleted_at"}
    _fields(revision, {"native_id", "operation", "revision_sha256", "locators"} | payload_fields)
    _match(revision["native_id"], r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
    native = str(UUID(revision["native_id"]))
    _sha(revision["revision_sha256"])
    if revision["operation"] != operation:
        raise ContractError("Snapshot revision operation mismatch")
    locators = revision["locators"]
    if not isinstance(locators, list) or not locators:
        raise ContractError("Missing revision locators")
    for value in locators:
        _match(value, r"/(?:[^~]|~[01])*")
    if locators != sorted(set(locators)):
        raise ContractError("Unordered or repeated revision locators")

    scope = snapshot["scope"]
    key = identifier("observation", scope["subject_id"], scope["source_instance"], native)
    return key, revision


def _project_observation(member, revision, key, snapshot, start, end):
    obs = revision["observation"]
    _fields(obs, OBSERVATION_FIELDS)
    first, last = (_clock(obs[k]) for k in ("event_start", "event_end"))
    if not start <= first < end or not first <= last <= end:
        raise ContractError("Observation outside snapshot interval")
    _clock(obs["collector_received_at"])
    for original, normalized in (("original_start", "event_start"), ("original_end", "event_end"),
                                 ("original_received_at", "collector_received_at")):
        if _date(obs[original]) != obs[normalized]:
            raise ContractError("Normalized measurement clock mismatch")
    for name in ("device_id", "calibration_id", "source_available_at"):
        if obs[name] is not None:
            raise ContractError("Unsupported capture provenance assertion")
    for name in ("source_name", "bundle_id"):
        if obs[name] is not None:
            _match(obs[name], r"[\s\S]+")

    channel, unit, epistemic = (obs[k] for k in ("channel", "unit", "epistemic_type"))
    for value in (channel, unit, epistemic):
        _match(value, r"[a-z_]+")
    classification = CLASSIFICATIONS.get((channel, unit, epistemic))
    if not classification or obs["classification_basis"] != classification or obs["original_unit"] != unit:
        raise ContractError("Unsupported observation classification or unit")
    if classification == "independent_measured_evidence":
        _sha(obs["classification_evidence_sha256"])
    elif obs["classification_evidence_sha256"] is not None:
        raise ContractError("Unexpected classification evidence")

    _match(obs["value"], r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?")
    if obs["value"] == "-0" or _decimal(obs["original_value"]) != obs["value"]:
        raise ContractError("Normalized measurement value mismatch")
    source_fact = {
        "channel": channel, "value": obs["value"], "unit": unit,
        "start": _decimal(obs["original_start"]), "end": _decimal(obs["original_end"]),
        "source_name": obs["source_name"], "bundle_id": obs["bundle_id"],
    }
    scope = snapshot["scope"]
    source_hash = revision["revision_sha256"]
    if digest(["mse.source-revision/0.2", scope, revision["native_id"], "upsert", source_fact]) != source_hash:
        raise ContractError("Observation source revision digest mismatch")
    normalized = {k: obs[k] for k in PROCESSING_FIELDS}
    processing_hash = digest(["mse.processing-revision/0.2", source_hash, snapshot["normalizer_version"], normalized])
    if processing_hash != member["processing_revision_sha256"]:
        raise ContractError("Observation processing revision digest mismatch")

    reason = None
    if epistemic == "unknown":
        reason = "heart_rate_derivation_unknown"
    elif epistemic == "measured":
        # This lane has no independent classification evidence resolver.
        reason = "heart_rate_classification_evidence_unverified"
    elif not 0 < float(obs["value"]) < float("inf"):
        reason = "scalar_unrepresentable_in_reference"
    if reason:
        return None, {"source_revision_sha256": source_hash, "reason": reason}

    return {
        **{k: obs[k] for k in ("channel", "value", "unit", "event_start", "event_end", "epistemic_type")},
        "schema_version": "mse.observation/0.1",
        "observation_id": key, "native_id": revision["native_id"],
        "subject_id": scope["subject_id"], "source_instance": scope["source_instance"],
        "received_at": obs["collector_received_at"], "context": "unknown",
        "provenance": {
            **{k: obs[k] for k in ("bundle_id", "source_name", "device_id", "calibration_id")},
            "method": "HealthKit SDNN", "received_at_semantics": "collector_receipt",
            "source_revision_sha256": source_hash, "processing_revision_sha256": processing_hash,
        },
        "quality_flags": ["measurement_error_unqualified", "source_availability_unknown"],
    }, None


def _deletion(revision, scope):
    tokens = revision["original_deleted_at"]
    if not isinstance(tokens, list) or not tokens:
        raise ContractError("Missing original deletion time")
    decimals = {_decimal(token) for token in tokens}
    if tokens != sorted(set(tokens)) or len(decimals) != 1:
        raise ContractError("Ambiguous original deletion time")
    original = next(iter(decimals))
    deleted = revision["deleted_at"]
    if utc(_clock(deleted)) != _date(original):
        raise ContractError("Normalized deletion clock mismatch")
    preimage = ["mse.source-revision/0.2", scope, revision["native_id"], "delete", original]
    if digest(preimage) != revision["revision_sha256"]:
        raise ContractError("Deletion source revision digest mismatch")
    return deleted


def _project(snapshot):
    start, end = (_clock(snapshot[k]) for k in ("measurement_start", "measurement_end"))
    cutoff = snapshot["knowledge_cutoff_sequence"]
    if start >= end or type(cutoff) is not int or not 0 <= cutoff <= SAFE_INTEGER:
        raise ContractError("Invalid snapshot interval or cutoff")

    receipts, sequences, revisions = {}, {}, set()
    tombstones, active, losses = {}, [], []
    seen_active, deleted_keys = set(), set()
    for field, operation in (("tombstones", "delete"), ("observations", "upsert")):
        previous = None
        for member in snapshot[field]:
            key, revision = _member(member, operation, snapshot)
            order = (revision["native_id"], revision["revision_sha256"])
            if previous is not None and order <= previous:
                raise ContractError("Unordered or repeated snapshot member")
            previous = order
            pf_id = member["pf001_revision_id"]
            if pf_id in revisions:
                raise ContractError("Repeated PF-001 revision identity")
            revisions.add(pf_id)
            binding = {k: member[k] for k in COMMIT_FIELDS}
            if sequences.setdefault(member["commit_sequence"], member["receipt_id"]) != member["receipt_id"]:
                raise ContractError("Conflicting snapshot commitment sequence")
            if receipts.setdefault(member["receipt_id"], binding) != binding:
                raise ContractError("Conflicting snapshot receipt identity")
            if operation == "delete":
                deleted = _deletion(revision, snapshot["scope"])
                deleted_keys.add(key)
                if (key, deleted) in tombstones:
                    losses.append({"source_revision_sha256": order[1], "reason": "reference_deletion_time_collision"})
                tombstones[key, deleted] = {"observation_id": key, "deleted_at": deleted}
                continue
            if key in seen_active or key in deleted_keys:
                raise ContractError("Conflicting active snapshot member")
            seen_active.add(key)
            observation, loss = _project_observation(member, revision, key, snapshot, start, end)
            if loss:
                losses.append(loss)
            else:
                active.append(observation)
    return {
        "schema_version": "mse.replay/0.1", "synthetic": True, "observations": active,
        "tombstones": [tombstones[k] for k in sorted(tombstones)],
    }, losses


def select_fact_sighting(sightings, cutoff, *, normalizer_version):
    """Select one fact from reopened (normalizer_version, member) pairs at cutoff.

    A missing eligible representative returns None. For an eligible upsert with
    no requested materialization, the producer records normalizer_unavailable.
    """
    if type(cutoff) is not int or not 0 <= cutoff <= SAFE_INTEGER:
        raise ContractError("Invalid sighting cutoff")
    _token(normalizer_version)

    identity = None
    materializations = {}
    by_sequence = {}
    processing = set()
    eligible = []
    for version, member in sightings:
        sequence = member["commit_sequence"]
        if type(sequence) is not int or not 1 <= sequence <= SAFE_INTEGER:
            raise ContractError("Invalid sighting commitment")
        if sequence > cutoff:
            continue

        revision = member["source_revision"]
        fact = (revision["native_id"], revision["operation"], revision["revision_sha256"])
        if identity is None:
            identity = fact
        if fact != identity:
            raise ContractError("Cannot merge sightings of distinct revisions")
        receipt_id = member["receipt_id"]
        if by_sequence.setdefault(sequence, receipt_id) != receipt_id:
            raise ContractError("Conflicting sighting commitment sequence")

        upsert = revision["operation"] == "upsert"
        if upsert and version != normalizer_version:
            continue
        encoded = canonical(member)
        if materializations.setdefault(sequence, encoded) != encoded:
            raise ContractError("Unequal sightings under one receipt")
        if upsert:
            processing.add(member["processing_revision_sha256"])
        eligible.append(member)

    if len(processing) > 1:
        raise ContractError("Ambiguous processing revisions for requested normalizer")
    return min(eligible, key=lambda member: member["commit_sequence"], default=None)


def replay_snapshot(
    snapshot_bytes: bytes, *, expected_scope: dict, expected_archive_id: str,
    max_bytes: int, max_members: int,
    verify_membership: Callable[[str, dict, dict], bool],
) -> dict:
    """Validate and replay the projection derived from one scoped synthetic snapshot."""
    snapshot = _read_snapshot(snapshot_bytes, max_bytes, max_members)
    if snapshot["scope"] != expected_scope or snapshot["archive_id"] != expected_archive_id:
        raise ContractError("Snapshot does not match expected scope and archive")
    projection, losses = _project(snapshot)
    # Standalone reference callers can verify selected membership independently.
    for field in ("observations", "tombstones"):
        for member in snapshot[field]:
            if verify_membership(snapshot["archive_id"], dict(snapshot["scope"]), deepcopy(member)) is not True:
                raise ContractError("Snapshot member not verified in reopened authoritative ledger")
    return _run_snapshot(snapshot_bytes, snapshot, projection, losses)


def _replay_validated_snapshot(snapshot_bytes, snapshot):
    projection, losses = _project(snapshot)
    return _run_snapshot(snapshot_bytes, snapshot, projection, losses)


def _run_snapshot(snapshot_bytes, snapshot, projection, losses):
    result = _replay_projection(snapshot_bytes, canonical(projection).encode("utf-8"))
    lineage = result["lineage"]
    lineage.update(
        snapshot_manifest_sha256=snapshot["snapshot_sha256"],
        native_projection_sha256=digest(["mse.native-projection/0.2", projection]),
        snapshot_scope=snapshot["scope"], archive_id=snapshot["archive_id"],
        knowledge_cutoff_sequence=snapshot["knowledge_cutoff_sequence"],
        normalizer_version=snapshot["normalizer_version"],
        mapping_version=MAPPING_VERSION, mapping_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        measurement_interval=[snapshot["measurement_start"], snapshot["measurement_end"]],
        observation_revisions=[
            {**{k: member[k] for k in COMMIT_FIELDS | {"pf001_revision_id", "processing_revision_sha256"}},
             **{k: member["source_revision"][k] for k in ("native_id", "revision_sha256")},
             **{k: member["source_revision"]["observation"][k] for k in ("collector_received_at", "source_available_at")}}
            for member in snapshot["observations"]
        ],
        deletion_facts=snapshot["tombstones"],
    )
    result.update(result_id="derived:" + digest(lineage), coverage=snapshot["coverage"],
                  input_losses=snapshot["losses"], projection_losses=losses)
    return result
