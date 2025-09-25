#!/usr/bin/env python3
import os
import numpy as np
import scripts.weyland_hash as wh


def load_yaml(p):
    try:
        import yaml

        with open(p, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _cfg():
    return (load_yaml("content/weyland.yaml") or {}).get("weyland", {})


def _concat_context(reasons: str, category: str):
    # include segment name if available
    seg = "baseline-you"
    try:
        import scripts.acheron_runtime as a

        seg, _ = a.infer_segment()
    except Exception:
        pass
    parts = []
    if reasons:
        parts.append(reasons)
    if category:
        parts.append(category)
    if seg:
        parts.append(seg)
    return " | ".join(parts)


# quick text lookup: use Lambert to get the actual micro-copy for an arm
def _text_for_arm(arm: str, tone_hint: str, reasons: str):
    try:
        import scripts.lambert_runtime as L

        # category from arm
        p = (arm or "").split("|")
        cat = p[3] if len(p) > 3 else ""
        tone = tone_hint if tone_hint and tone_hint != "auto" else "gentle"
        txt, meta = L.pick_text(cat, tone, reasons)
        return txt, (meta or {})
    except Exception:
        return "Do a tiny reset.", {}


# cache for index
_CACHE = {"ids": None, "vecs": None, "map": {}}


def _ensure_index():
    if not bool((_cfg().get("use_index", True))):
        return False
    if _CACHE["ids"] is not None:
        return True
    if not os.path.exists("out/weyland_index.npz"):
        try:
            import scripts.weyland_index as WI

            WI.main()
        except Exception:
            return False
    try:
        d = np.load("out/weyland_index.npz", allow_pickle=False)
        ids = d["ids"]
        vecs = d["vecs"]
        _CACHE["ids"] = ids
        _CACHE["vecs"] = vecs
        _CACHE["map"] = {ids[i]: vecs[i] for i in range(len(ids))}
        return True
    except Exception:
        return False


def score_arm(arm: str, tone_hint: str, reasons: str) -> float:
    ctx = _concat_context(reasons, (arm or "").split("|")[3] if arm else "")
    v_ctx = wh.embed(ctx)
    txt, meta = _text_for_arm(arm, tone_hint, reasons)
    v_txt = None
    if _ensure_index():
        tid = str(meta.get("id", ""))
        v_txt = _CACHE["map"].get(tid)
    if v_txt is None:
        v_txt = wh.embed(txt)
    sim = wh.cosine(v_ctx, v_txt)
    # normalize cosine [-1,1] -> [0,1]
    return (sim + 1.0) / 2.0
