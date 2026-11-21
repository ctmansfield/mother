"""Derive an advisory handoff from a trusted directive and pinned receipt bytes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
import hashlib
import json
import re

SHA256 = re.compile(r"[0-9a-f]{64}")
RECEIPT_FIELDS = {
    "receipt_id",
    "issuer",
    "task_id",
    "revision",
    "artifact_sha256",
    "observed_at",
    "expires_at",
    "verified_state",
}


@dataclass(frozen=True)
class ReceiptPin:
    issuer: str
    receipt_id: str
    sha256: str


@dataclass(frozen=True)
class HandoffRule:
    status: str
    next_owner: str
    next_action_code: str


@dataclass(frozen=True)
class Directive:
    task_id: str
    revision: str
    artifact_sha256: str
    valid_from: int
    expires_at: int
    pins: tuple[ReceiptPin, ...]
    state_rules: Mapping[str, HandoffRule]


@dataclass(frozen=True)
class VerifiedHandoff:
    status: str
    next_owner: str
    evidence_ids: tuple[str, ...]
    verified_state: str
    next_action_code: str


@dataclass(frozen=True)
class Result:
    disposition: str
    reason: str | None = None
    handoff: VerifiedHandoff | None = None


@dataclass(frozen=True)
class CandidateReview:
    disposition: str
    verified_handoff: VerifiedHandoff | None
    defects: tuple[str, ...] = ()


def _unique_object(pairs):
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise ValueError("duplicate JSON key")
    return obj


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _digest(value):
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def _timestamp(value):
    return type(value) is int and value >= 0


def _receipt(raw):
    obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(obj, dict) or obj.keys() != RECEIPT_FIELDS:
        raise ValueError("unexpected receipt fields")
    if not all(
        _nonempty(obj[key])
        for key in ("receipt_id", "issuer", "task_id", "revision", "verified_state")
    ):
        raise ValueError("invalid receipt identifier")
    if not _digest(obj["artifact_sha256"]):
        raise ValueError("invalid artifact pin")
    if not (
        _timestamp(obj["observed_at"])
        and _timestamp(obj["expires_at"])
        and obj["observed_at"] < obj["expires_at"]
    ):
        raise ValueError("invalid receipt time window")
    return obj


def derive_handoff(
    directive: Directive, receipts: Iterable[bytes], *, as_of: int
) -> Result:
    """Bind one current receipt per required issuer; an eligible result is advisory."""
    if not _timestamp(as_of):
        return Result("HOLD", "invalid_as_of")
    pins = {pin.issuer: pin for pin in directive.pins}
    receipt_ids = {pin.receipt_id for pin in directive.pins}
    if (
        not _nonempty(directive.task_id)
        or not _nonempty(directive.revision)
        or not _digest(directive.artifact_sha256)
        or not _timestamp(directive.valid_from)
        or not _timestamp(directive.expires_at)
        or directive.valid_from >= directive.expires_at
        or not pins
        or len(pins) != len(directive.pins)
        or len(receipt_ids) != len(pins)
        or any(
            not _nonempty(pin.issuer)
            or not _nonempty(pin.receipt_id)
            or not _digest(pin.sha256)
            for pin in directive.pins
        )
    ):
        return Result("HOLD", "invalid_directive")
    if not directive.valid_from <= as_of < directive.expires_at:
        return Result("HOLD", "directive_not_current")

    seen = set()
    states = set()
    for raw in receipts:
        if not isinstance(raw, bytes):
            return Result("HOLD", "malformed_receipt")
        try:
            receipt = _receipt(raw)
        except (ValueError, RecursionError):
            return Result("HOLD", "malformed_receipt")
        issuer = receipt["issuer"]
        pin = pins.get(issuer)
        if pin is None:
            return Result("HOLD", "unexpected_issuer")
        if issuer in seen:
            return Result("HOLD", "duplicate_issuer")
        if hashlib.sha256(raw).hexdigest() != pin.sha256:
            return Result("HOLD", "receipt_digest_mismatch")
        if (
            receipt["receipt_id"] != pin.receipt_id
            or receipt["task_id"] != directive.task_id
            or receipt["revision"] != directive.revision
            or receipt["artifact_sha256"] != directive.artifact_sha256
        ):
            return Result("HOLD", "receipt_binding_mismatch")
        if not receipt["observed_at"] <= as_of < receipt["expires_at"]:
            return Result("HOLD", "receipt_not_current")
        seen.add(issuer)
        states.add(receipt["verified_state"])

    if seen != pins.keys():
        return Result("HOLD", "missing_receipt")
    if len(states) != 1:
        return Result("HOLD", "conflicting_states")
    (state,) = states
    rule = directive.state_rules.get(state)
    if (
        rule is None
        or rule.status not in ("HOLD", "PROCEED")
        or not _nonempty(rule.next_owner)
        or not _nonempty(rule.next_action_code)
    ):
        return Result("HOLD", "missing_or_invalid_state_rule")
    return Result(
        "ELIGIBLE_FOR_REVIEW",
        handoff=VerifiedHandoff(
            status=rule.status,
            next_owner=rule.next_owner,
            evidence_ids=tuple(pin.receipt_id for pin in directive.pins),
            verified_state=state,
            next_action_code=rule.next_action_code,
        ),
    )


def check_candidate(result: Result, candidate: object) -> CandidateReview:
    """Check a JSON-shaped proposal without granting execution authority."""
    if result.disposition != "ELIGIBLE_FOR_REVIEW" or result.handoff is None:
        return CandidateReview("HOLD", None, ("unverified_receipts",))
    expected = asdict(result.handoff)
    expected["evidence_ids"] = list(result.handoff.evidence_ids)
    if not isinstance(candidate, dict):
        return CandidateReview("HOLD", result.handoff, ("malformed_candidate",))
    defects = tuple(
        field
        for field, value in expected.items()
        if type(candidate.get(field)) is not type(value) or candidate[field] != value
    )
    if candidate.keys() - expected.keys():
        defects += ("unexpected_candidate_fields",)
    disposition = "HOLD" if defects else "ELIGIBLE_FOR_REVIEW"
    return CandidateReview(disposition, result.handoff, defects)
