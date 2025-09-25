#!/usr/bin/env python3
import os
import hashlib
import time
from datetime import datetime

EXPOSURES_CSV = os.path.join("out", "experiments_log.csv")
FEEDBACK_CSV = os.path.join("out", "experiments_feedback.csv")
ASSIGN_JSON = os.path.join("out", "hudson_assignments.json")


def _ensure_files():
    os.makedirs("out", exist_ok=True)
    if not os.path.exists(EXPOSURES_CSV):
        with open(EXPOSURES_CSV, "w") as f:
            f.write("ts,experiment_id,variant,arm,p,threshold,allowed,impression_id\n")
    if not os.path.exists(FEEDBACK_CSV):
        with open(FEEDBACK_CSV, "w") as f:
            f.write("ts,arm,reward\n")


def _load_yaml(path):
    try:
        import yaml

        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def load_experiments(path="content/experiments.yaml"):
    cfg = _load_yaml(path) or {}
    exps = cfg.get("experiments") or []
    for e in exps:
        vs = e.get("variants", {}) or {}
        total = sum(float(v.get("weight", 0.0)) for v in vs.values()) or 1.0
        for k, v in vs.items():
            v["weight_norm"] = float(v.get("weight", 0.0)) / total
    return exps


def is_active(exp, now):
    if not exp.get("active", True):
        return False
    try:
        s = exp.get("start")
        e = exp.get("end")
        if s and now.date() < datetime.fromisoformat(s).date():
            return False
        if e and now.date() > datetime.fromisoformat(e).date():
            return False
        return True
    except Exception:
        return True


def subject_id():
    return os.environ.get("MOTHER_SUBJECT") or os.uname().nodename


def _u01(keybytes: bytes):
    return int(hashlib.sha1(keybytes).hexdigest()[:8], 16) / 0xFFFFFFFF


def in_traffic(exp, subj):
    t = float(exp.get("traffic", 1.0))
    if t >= 1.0:
        return True
    if t <= 0.0:
        return False
    h = _u01(f"{exp.get('id')}|{subj}|traffic".encode("utf-8"))
    return h <= t


def assign_variant(exp, subject=None):
    subject = subject or subject_id()
    key = f"{exp.get('id')}|{subject}".encode("utf-8")
    h = _u01(key)
    acc = 0.0
    for name, meta in exp.get("variants", {}).items():
        acc += float(meta.get("weight_norm", 0.0))
        if h <= acc:
            return name, meta
    name, meta = next(iter(exp.get("variants", {}).items()))
    return name, meta


def log_exposure(exp_id, variant, arm, p, threshold, allowed, impression_id=None):
    _ensure_files()
    if impression_id is None:
        impression_id = (
            f"{int(time.time())}-{hashlib.md5(arm.encode()).hexdigest()[:6]}"
        )
    with open(EXPOSURES_CSV, "a") as f:
        f.write(
            f"{int(time.time())},{exp_id},{variant},{arm},{p:.4f},{threshold:.2f},{int(bool(allowed))},{impression_id}\n"
        )
    return impression_id


def log_feedback(arm, reward):
    _ensure_files()
    with open(FEEDBACK_CSV, "a") as f:
        f.write(f"{int(time.time())},{arm},{int(reward)}\n")


def choose_for_category(category, now=None):
    now = now or datetime.now()
    subj = subject_id()
    for exp in load_experiments() or []:
        if (
            exp.get("category") == category
            and is_active(exp, now)
            and in_traffic(exp, subj)
        ):
            var_key, var_meta = assign_variant(exp, subj)
            return exp, var_key, var_meta
    return None, None, None
