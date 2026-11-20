"""OU reference filter for observed scalar deviations, not identified biochemistry."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import math
from statistics import mean, variance

from . import MODEL_VERSION, implementation_sha256
from .contracts import ContractError, digest, identifier, timestamp

PARAMETERS = {
    "heart_rate": {"variance_floor": 4.0, "equilibrium_variance": 100.0, "tau_seconds": 7200.0, "unit": "bpm"},
    "hrv_sdnn": {"variance_floor": 0.09, "equilibrium_variance": 0.16, "tau_seconds": 21600.0, "unit": "log(ms/ms)"},
    "glucose": {"variance_floor": 0.25, "equilibrium_variance": 4.0, "tau_seconds": 3600.0, "unit": "mmol/L"},
}


@dataclass(frozen=True)
class Config:
    min_baseline: int = 8
    baseline_window_seconds: float = 604800.0
    max_gap_seconds: float = 21600.0

    def validate(self):
        if isinstance(self.min_baseline, bool) or self.min_baseline < 2:
            raise ContractError("Baseline requires at least two prior samples")
        if not math.isfinite(self.baseline_window_seconds) or self.baseline_window_seconds <= 0:
            raise ContractError("Invalid baseline window")
        if not math.isfinite(self.max_gap_seconds) or self.max_gap_seconds <= 0:
            raise ContractError("Invalid maximum gap")
        return self


def predict(mean_value, posterior_variance, delta_seconds, *, tau, equilibrium_variance):
    if delta_seconds < 0:
        raise ContractError("Filter time must increase")
    a = math.exp(-delta_seconds / tau)
    return a * mean_value, a * a * posterior_variance + equilibrium_variance * (1 - a * a)


def _transformed(record):
    value = float(record["value"])
    return math.log(value) if record["channel"] == "hrv_sdnn" else value


BLOCKING_QUALITY_FLAGS = frozenset({
    "known_motion_artifact", "invalid_measurement", "sensor_error",
    "invalid_calibration", "clock_error", "corrupt_record",
})
REPLAY_MODE = "retrospective_snapshot"


def _check_mode(mode):
    if mode != REPLAY_MODE:
        raise ContractError("Only retrospective_snapshot replay is implemented; online/source-as-available claims are unsupported")


def _configuration(config):
    return {"config": asdict(config), "fixed_channel_parameters": PARAMETERS,
            "reference_time_policy": "aggregate_interval_end",
            "availability_policy": REPLAY_MODE,
            "quality_policy": "exclude_known_invalid_and_propagate_all_ancestry",
            "blocking_quality_flags": sorted(BLOCKING_QUALITY_FLAGS),
            "interval_policy": "complete_nonoverlapping_intervals_only"}


def estimate(records, config=None, *, replay_mode=REPLAY_MODE):
    _check_mode(replay_mode)
    config = (config or Config()).validate()
    code_hash = implementation_sha256()
    model_config_hash = digest(_configuration(config))
    groups = defaultdict(list)
    by_id = {r["observation_id"]: r for r in records}
    for record in records:
        provenance = record["provenance"]
        duration = (timestamp(record["event_end"]) - timestamp(record["event_start"])).total_seconds()
        group = (record["subject_id"], record["source_instance"], record["channel"], record["context"],
                 provenance.get("bundle_id"), provenance.get("device_id"),
                 provenance.get("method"), duration, provenance.get("acquisition_window_seconds"),
                 provenance.get("calibration_id"))
        groups[group].append(record)
    outputs = []
    for group in sorted(groups, key=repr):
        series = sorted(groups[group], key=lambda r: (r["event_end"], r["observation_id"]))
        history, rejected_history = [], []
        posterior = None
        filter_lineage = []
        for record in series:
            t = timestamp(record["event_end"])
            interval_start = timestamp(record["event_start"])
            prior = [r for r in history
                     if timestamp(r["event_end"]) <= interval_start
                     and 0 < (t - timestamp(r["event_end"])).total_seconds() <= config.baseline_window_seconds]
            exclusions = [(r, flags) for r, flags in rejected_history
                          if 0 <= (t - timestamp(r["event_end"])).total_seconds() <= config.baseline_window_seconds]
            blocking = sorted(set(record["quality_flags"]) & BLOCKING_QUALITY_FLAGS)
            duplicate_time = bool(history and timestamp(history[-1]["event_end"]) == t)
            overlap = bool(history and interval_start < timestamp(history[-1]["event_end"]))
            rejection = ("known_invalid_measurement_quality" if blocking else
                         "simultaneous_samples_not_assumed_independent" if duplicate_time else
                         "overlapping_acquisition_intervals" if overlap else None)
            if rejection:
                exclusions.append((record, blocking or [rejection]))
            p = PARAMETERS[record["channel"]]
            state = {
                "schema_version": "mse.state/0.1", "state_id": None,
                "model_version": MODEL_VERSION, "implementation_sha256": code_hash,
                "model_configuration_sha256": model_config_hash,
                "subject_id": group[0], "source_instance": group[1], "channel": group[2],
                "context": group[3], "observation_reference_time": record["event_end"],
                "observation_reference_policy": "aggregate_interval_end",
                "availability_policy": REPLAY_MODE,
                "historical_source_availability_established": False,
                "historical_mother_availability_established": False,
                "measurement_stratum": {"bundle_id": group[4], "device_id": group[5], "method": group[6],
                                        "observed_interval_seconds": group[7],
                                        "declared_acquisition_window_seconds": group[8], "calibration_id": group[9]},
                "epistemic_type": "statistically_inferred", "state_kind": "observed_signal_deviation",
                "status": "unknown", "reason": rejection or "insufficient_prior_baseline",
                "mean": None, "variance": None, "reference_95_interval": None,
                "unit": p["unit"], "baseline_count": len(prior), "baseline": None,
                "supporting_observation_ids": [record["observation_id"]],
                "baseline_observation_ids": [r["observation_id"] for r in prior],
                "excluded_observation_ids": sorted({r["observation_id"] for r, _ in exclusions}),
                "excluded_quality_flags": sorted({flag for _, flags in exclusions for flag in flags}),
                "current_quality_flags": sorted(set(record["quality_flags"])),
                "quality_policy": "exclude_known_invalid_and_propagate_all_ancestry",
                "uncertainty_status": "uncalibrated_reference_model", "mechanism_status": "unknown",
                "limits": ["No biochemical cause identified", "No sympathetic/vagal fraction inferred",
                           "Parameters are illustrative, not fitted or clinically validated",
                           "Baseline uncertainty uses an independence approximation; serial correlation is unmodeled",
                           "Retrospective event-time estimate; source receipts may occur after this reference time; not an online or historical as-available state"],
            }
            if group[3] == "unknown":
                state["limits"].append("Acquisition conditions absent; baseline is not adjusted for posture, respiration, activity, sleep or meals")
            if rejection is None and len(prior) >= config.min_baseline:
                values = [_transformed(r) for r in prior]
                baseline = mean(values)
                baseline_variance = max(variance(values), p["variance_floor"]) / len(values)
                state["baseline"] = {"mean": baseline, "variance": baseline_variance,
                                     "method": "prior complete nonoverlapping intervals; sliding-window mean in transformed space"}
                dt = None if posterior is None else (t - posterior[2]).total_seconds()
                stale = dt is not None and dt > config.max_gap_seconds
                if posterior is None or stale:
                    m, v = 0.0, p["equilibrium_variance"]
                    filter_lineage = []
                else:
                    m, v = predict(posterior[0], posterior[1], dt,
                                   tau=p["tau_seconds"], equilibrium_variance=p["equilibrium_variance"])
                prior_variance = v
                measurement_variance = p["variance_floor"] + baseline_variance
                innovation = _transformed(record) - baseline - m
                gain = v / (v + measurement_variance)
                m += gain * innovation
                v = (1 - gain) * v
                posterior = (m, v, t)
                filter_lineage = sorted(set(filter_lineage) | {record["observation_id"]}
                                        | {r["observation_id"] for r in prior})
                state.update(status="unknown" if stale else "estimated",
                             reason="gap_reset_reacquisition" if stale else "reference_filter_update",
                             mean=None if stale else m, variance=None if stale else v,
                             reference_95_interval=None if stale else [m - 1.96 * math.sqrt(v), m + 1.96 * math.sqrt(v)],
                             prediction_variance=prior_variance,
                             supporting_observation_ids=filter_lineage.copy())
            baseline_ids = set(state["baseline_observation_ids"])
            support_ids = set(state["supporting_observation_ids"]) | baseline_ids
            ancestor_ids = support_ids - {record["observation_id"]}
            state["baseline_quality_flags"] = sorted({flag for key in baseline_ids for flag in by_id[key]["quality_flags"]})
            state["filter_ancestor_quality_flags"] = sorted({flag for key in ancestor_ids for flag in by_id[key]["quality_flags"]})
            state["support_quality_flags"] = sorted({flag for key in support_ids for flag in by_id[key]["quality_flags"]})
            state["measurement_quality_flags"] = sorted(set(state["support_quality_flags"]) | set(state["excluded_quality_flags"]))
            state["support_source_receipt_max"] = max(by_id[key]["received_at"] for key in support_ids)
            state["state_id"] = identifier("state", MODEL_VERSION, _configuration(config), state)
            outputs.append(state)
            if rejection:
                rejected_history.append((record, blocking or [rejection]))
            else:
                history.append(record)
    return sorted(outputs, key=lambda state: (state["observation_reference_time"], state["state_id"]))


def replay(store, config=None, source_receipt_cutoff=None, *, replay_mode=REPLAY_MODE):
    _check_mode(replay_mode)
    config = (config or Config()).validate()
    records = store.active_observations(source_receipt_cutoff)
    evidence = store.evidence_manifest()
    config_body = _configuration(config)
    dataset_hash = digest({"observations": records, "evidence": evidence,
                           "source_receipt_cutoff": source_receipt_cutoff})
    config_hash = digest(config_body)
    code_hash = implementation_sha256()
    result = {
        "schema_version": "mse.run/0.1", "model_version": MODEL_VERSION,
        "run_id": identifier("run", dataset_hash, MODEL_VERSION, config_hash, code_hash),
        "implementation_sha256": code_hash,
        "dataset_hash": dataset_hash, "config_hash": config_hash, "configuration": config_body,
        "replay_mode": REPLAY_MODE,
        "availability_policy": "retrospective_snapshot_not_historical_as_available",
        "snapshot_filter_semantics": "One global source-receipt and completed-interval cutoff; not a separate historical knowledge set at each state time",
        "historical_source_availability_established": False,
        "source_receipt_cutoff": source_receipt_cutoff,
        "historical_mother_availability_established": False,
        "evidence_manifest": evidence, "active_observation_count": len(records),
        "states": estimate(records, config),
        "unknown_dimensions": ["insulin_action", "hepatic_glucose_production", "substrate_oxidation",
                               "mitochondrial_function", "inflammation", "microbial_flux", "receptor_occupancy"],
        "measurement_request": {
            "mode": "observation_only", "reason": "HR/SDNN patterns are compatible with several mechanisms",
            "suggested_observation": "Record posture, recent exertion, breathing conditions, sleep and meal timing alongside repeated observations",
            "expected_discrimination": "Separate context-associated signal variation from a persistent unexplained deviation",
            "expected_information_gain": None, "selection_method": "declared heuristic, not validated information gain",
            "does_not_establish": "Any specific autonomic, endocrine, inflammatory or mitochondrial cause",
        },
        "intervention_authority": "none",
    }
    store.save_run(result)
    return result
