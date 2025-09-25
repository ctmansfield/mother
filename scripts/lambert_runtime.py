#!/usr/bin/env python3
import os
import json
import re
import hashlib


def load_yaml(path):
    try:
        import yaml

        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


WORD = re.compile(r"[A-Za-z][A-Za-z0-9']+")


def tokenize(s, stop):
    toks = [t.lower() for t in WORD.findall(s or "")]
    return [t for t in toks if t not in stop]


def current_segment():
    try:
        import scripts.acheron_runtime as a

        seg, _ = a.infer_segment()
        return seg
    except Exception:
        return "baseline-you"


def ensure_index():
    if not os.path.exists("out/lambert_index.json"):
        try:
            import scripts.lambert_index as b

            b.main()
        except Exception:
            json.dump({"index": []}, open("out/lambert_index.json", "w"))


def pick_text(category: str, tone: str, reasons: str = ""):
    cfg = (load_yaml("content/lambert.yaml") or {}).get("lambert", {})
    w_kw = float(cfg.get("weights", {}).get("keyword_overlap", 0.7))
    w_tn = float(cfg.get("weights", {}).get("tone_match", 0.2))
    w_seg = float(cfg.get("weights", {}).get("segment_match", 0.1))
    stop = set(cfg.get("stopwords") or [])
    topn = int(cfg.get("topn", 5))
    seg = current_segment()
    ensure_index()
    data = (
        json.load(open("out/lambert_index.json"))
        if os.path.exists("out/lambert_index.json")
        else {"index": []}
    )
    idx = [r for r in (data.get("index") or []) if r.get("category") == category]
    if not idx:
        # fallback to plain reminders.yaml
        tpl = (load_yaml("content/templates/reminders.yaml") or {}).get(category) or []
        return (tpl[0] if tpl else "Do a tiny reset."), {
            "score": 0.0,
            "reason": "fallback_no_index",
            "segment": seg,
        }
    ctx_tokens = tokenize(reasons or "", stop)
    # score = w_kw * overlap + w_tn * tone_match + w_seg * seg_match
    scored = []
    for r in idx:
        toks = set(r.get("tokens") or [])
        overlap = (
            len(set(ctx_tokens) & toks) / max(1, len(set(ctx_tokens) | toks))
            if (ctx_tokens or toks)
            else 0.0
        )
        tone_match = 1.0 if (r.get("tone") and r.get("tone") == tone) else 0.0
        seg_match = 1.0 if (seg in (r.get("segments") or [])) else 0.0
        s = w_kw * overlap + w_tn * tone_match + w_seg * seg_match
        scored.append((s, r))
    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[:topn] if scored else []
    best = top[0][1] if top else idx[0]
    hid = best.get("id") or ""
    hh = hashlib.sha1(
        ((best.get("text", "") or "") + "|" + (best.get("category", "") or "")).encode(
            "utf-8"
        )
    ).hexdigest()[:12]
    return best.get("text", "Do a tiny reset."), {
        "id": hid,
        "hash": hh,
        "score": round((top[0][0] if top else 0.0), 4),
        "overlap_top": list((top[0][1].get("tokens") or [])[:3]) if top else [],
        "segment": seg,
        "tone_pref": tone,
    }
