#!/usr/bin/env python3
"""Bounded behavioral caller adapter. This module makes no network calls.

The external orchestrator supplies a local-only, timeout-bounded Ollama caller
and owns serialization, exact model identity, GPU residency and source checks.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time

try:
    from . import benchmark
except ImportError:
    import benchmark

MODEL = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$')
COMMIT = re.compile(r'^[0-9a-f]{40}$')
TELEMETRY_FIELDS = ('total_duration', 'load_duration', 'prompt_eval_count',
                    'prompt_eval_duration', 'eval_count', 'eval_duration')


class EnvelopeRefusal(ValueError):
    """A static adapter error code, safe to retain in the result record."""


def envelope(condition, code):
    if not condition:
        raise EnvelopeRefusal(code)


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_new(path, value):
    data = benchmark.canonical(value) + b'\n'
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def run_model(output_dir, model, model_digest, source_pin, call, seed=20261120):
    """Run exactly this pack's 24 serial cases, stopping on a caller refusal.

    call(model, prompt, options) must return an Ollama /api/generate dictionary.
    It MUST enforce a per-request timeout and raise on its own identity/GPU
    guard failure. The adapter never sees the protected key inside the caller.
    The output directory must not exist. A failed/interrupted run is retained;
    a retry needs a new directory. No role assignment is made from this screen.
    """
    benchmark.require(isinstance(model, str) and MODEL.fullmatch(model), 'model tag')
    benchmark.require(isinstance(model_digest, str) and benchmark.HEX.fullmatch(model_digest),
                      'full model digest required')
    benchmark.require(isinstance(source_pin, str) and COMMIT.fullmatch(source_pin),
                      'full source commit required')
    benchmark.require(type(seed) is int and 0 <= seed < 2**31 - 24, 'seed range')
    benchmark.require(callable(call), 'caller required')
    cases, key, pack_sha = benchmark.load_pack()
    output = Path(output_dir)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.chmod(output, 0o700)
    run = {
        'schema': 'fw00413.behavioral-run.v1', 'started_utc': utc(),
        'model': model, 'model_digest': model_digest, 'source_pin': source_pin,
        'pack_sha256': pack_sha, 'planned_cases': 24, 'max_requests': 24, 'seed': seed,
        'call_order': [case['id'] for case in cases],
        'options': {'temperature': 0, 'num_ctx': 4096, 'num_predict': 900},
        'gpu_verification': 'EXTERNAL_ORCHESTRATOR_REQUIRED',
        'rationale_review': 'NOT_AUTOMATICALLY_SCORED',
        'status': 'EXPERIMENT_ONLY_NOT_MODEL_ROLE_ASSIGNMENT'}
    write_new(output / 'run_manifest.json', run)
    records = []
    stop_reason = 'COMPLETED'
    fatal_hold = False
    record_path = output / 'records.jsonl'
    descriptor = os.open(record_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as ledger:
            for index, case in enumerate(cases):
                query = benchmark.prompt(case)
                options = dict(run['options'], seed=seed + index)
                started = time.monotonic()
                raw, request_ok, failure, failure_code = '', False, None, None
                completed_slot, response_type = False, None
                response_hash, response_bytes, retained, metadata = None, 0, '', {}
                try:
                    reply = call(model, query, options)
                    envelope(isinstance(reply, dict), 'INVALID_CALLER_ENVELOPE')
                    envelope(reply.get('model') == model, 'MODEL_IDENTITY_MISMATCH')
                    envelope(reply.get('done') is True, 'INCOMPLETE_GENERATION')
                    completed_slot = True
                    raw = reply.get('response')
                    response_type = type(raw).__name__
                    raw_bytes = raw.encode('utf-8') if isinstance(raw, str) else benchmark.canonical(raw)
                    response_hash, response_bytes = benchmark.sha(raw_bytes), len(raw_bytes)
                    retained = raw_bytes[:benchmark.MAX_RESPONSE].decode('utf-8', errors='replace')
                    metadata = {name: reply[name] for name in TELEMETRY_FIELDS
                                if type(reply.get(name)) is int and reply[name] >= 0}
                    if reply.get('done_reason') == 'length':
                        failure_code = 'TRUNCATED_GENERATION'
                    elif not isinstance(raw, str):
                        failure_code = 'RESPONSE_NOT_TEXT'
                    elif response_bytes > benchmark.MAX_RESPONSE:
                        failure_code = 'RESPONSE_BYTE_BUDGET'
                    request_ok = failure_code is None
                    if not request_ok:
                        failure = 'CompletedResponseFailure'
                except Exception as error:
                    # Preserve a bounded error class, not arbitrary exception text that
                    # could contain credentials or a remote response dump.
                    failure = type(error).__name__
                    failure_code = str(error) if isinstance(error, EnvelopeRefusal) else 'CALLER_ERROR'
                    stop_reason = 'CALLER_REFUSED_OR_REQUEST_FAILED'
                    fatal_hold = True
                result = benchmark.grade(raw if request_ok else '', case, key[case['id']])
                record = {
                    'schema': 'fw00413.behavioral-case-result.v1', 'sequence': index + 1,
                    'case_id': case['id'], 'role': case['role'], 'recorded_utc': utc(),
                    'source_pin': source_pin, 'pack_sha256': pack_sha,
                    'model': model, 'model_digest': model_digest,
                    'prompt_sha256': benchmark.sha(query.encode('utf-8')), 'options': options,
                    'request_ok': request_ok, 'request_failure_class': failure,
                    'request_failure_code': failure_code,
                    'completed_case_slot': completed_slot,
                    'elapsed_seconds': round(time.monotonic() - started, 6),
                    'raw_response_sha256': response_hash, 'raw_response_bytes': response_bytes,
                    'raw_response': retained, 'raw_response_type': response_type,
                    'ollama_timing': metadata, 'grade': result}
                records.append(record)
                ledger.write(benchmark.canonical(record) + b'\n')
                ledger.flush()
                os.fsync(ledger.fileno())
                if fatal_hold:
                    break
    except BaseException:
        stop_reason = 'INTERRUPTED_OR_LOCAL_FAILURE'
        fatal_hold = True
        raise
    finally:
        summary = benchmark.summarize(records, pack_sha)
        summary.update({
            'model': model, 'model_digest': model_digest, 'source_pin': source_pin,
            'completed_utc': utc(), 'planned_cases': 24,
            'complete': len(records) == 24 and not fatal_hold,
            'completed_case_slots': sum(row['completed_case_slot'] for row in records),
            'successful_requests': sum(row['request_ok'] for row in records),
            'fatal_hold': fatal_hold,
            'stop_reason': stop_reason, 'unattempted_cases': 24 - len(records),
            'gpu_verification': 'EXTERNAL_ORCHESTRATOR_REQUIRED',
            'records_sha256': hashlib.sha256(record_path.read_bytes()).hexdigest()})
        write_new(output / 'summary.json', summary)
    return summary
