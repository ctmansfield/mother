#!/usr/bin/env python3
import os, json, math, time
from datetime import datetime
try:
    import scripts.weyland_runtime as weyland
import scripts.gorman_runtime as gorman
    import numpy as np
except Exception:
    np=None

def load_yaml(path):
    try:
    import scripts.weyland_runtime as weyland
import scripts.gorman_runtime as gorman
        import yaml
        with open(path,'r') as f: return yaml.safe_load(f)
    except Exception:
        return None

def _cfg():
    return (load_yaml('content/nostromo.yaml') or {}).get('nostromo',{})

def _arm_parts(arm):
    p=(arm or '').split('|')
    return (p[0] if len(p)>0 else '', p[1] if len(p)>1 else '', p[2] if len(p)>2 else '', p[3] if len(p)>3 else '')

def _now_hour():
    return datetime.now().hour

def _vasquez_allowed(category):
    vs=load_yaml('content/vasquez_windows.yaml') or {}
    hours=(vs.get('windows') or {}).get(category) or []
    if not hours: return False
    return _now_hour() in set(hours)

def _uplift_for(arm):
    src=((_cfg().get('uplift_source') or {}).get('path') or 'content/ash_table.yaml')
    tab=(load_yaml(src) or {}).get('ash_table') or {}
    dp,tn,ch,ct=_arm_parts(arm)
    # table key is typically nested by category -> daypart -> tone -> channel
    try:
    import scripts.weyland_runtime as weyland
import scripts.gorman_runtime as gorman
        v = (((tab.get(ct) or {}).get(dp) or {}).get(tn) or {}).get(ch)
        if isinstance(v,(int,float)): return float(v)
    except Exception:
        pass
    return 0.0

def _pref_bonus(arm):
    try:
    import scripts.weyland_runtime as weyland
import scripts.gorman_runtime as gorman
        import scripts.acheron_runtime as a
        seg,bias=a.infer_segment()
        dp,tn,ch,ct=_arm_parts(arm)
        tone_pref  = (bias or {}).get('tone_pref',    ['gentle','humor','strict'])
        chan_pref  = (bias or {}).get('channel_pref', ['push','in_app'])
        b=_cfg().get('pref_bonus',0.02)
        bonus=0.0
        if tn==tone_pref[0]: bonus += b
        if ch==chan_pref[0]: bonus += b
        return bonus, seg
    except Exception:
        return 0.0, 'baseline-you'

def score_arms(candidates, ripley_probs, dallas_scores, threshold=0.28, reasons_str=''):
    cfg=_cfg()
    w_r=float(cfg.get('w_ripley',0.6))
    w_d=float(cfg.get('w_dallas',0.25))
    w_u=float(cfg.get('w_uplift',0.15))
    w_w=float(cfg.get('w_weyland',0.10))
    w_g=float(cfg.get('w_gorman',0.10))
    v_bonus=float(cfg.get('vasquez_bonus',0.03))
    min_p=float(cfg.get('min_p',0.05))
    use_thr=bool(cfg.get('use_threshold', True))

    out={}
    why={}
    for arm in candidates:
        p=float(ripley_probs.get(arm,0.0))
        d=float(dallas_scores.get(arm,0.0))
        u=_uplift_for(arm)
        if use_thr and p < threshold:  # hard gate during scoring
            out[arm]=-1e9
            why[arm]=[("below_threshold", -abs(threshold-p))]
            continue
        if p < min_p:
            out[arm]=-1e6
            why[arm]=[("min_p", -abs(min_p-p))]
            continue
        bonus=0.0
        reasons=[]
        if _vasquez_allowed(_arm_parts(arm)[3]):
            bonus+=v_bonus; reasons.append(("vasquez_window", v_bonus))
        pb, seg = _pref_bonus(arm)
        if pb>0: bonus+=pb; reasons.append(("pref_bonus", pb))
        # blended score
        w = 0.0
        try:
            w = weyland.score_arm(arm, _arm_parts(arm)[1], reasons_str)
        except Exception:
            w = 0.0
        g = 0.0
        try:
            g = gorman.score_arm(arm)
        except Exception:
            g = 0.0
        s = (w_r*p) + (w_d*d) + (w_u*u) + (w_w*w) + (w_g*g) + bonus
        out[arm]=s
        # pack explanation contributors
        reasons.extend([("ripley_p", w_r*p), ("dallas", w_d*d), ("uplift", w_u*u), ("weyland", w_w*w), ("gorman", w_g*g)])
        reasons.sort(key=lambda t: t[1], reverse=True)
        why[arm]=reasons[:int(cfg.get('explain_top',3))]
    return out, why

def pick(candidates, threshold, dallas_scores, ripley_probs, reasons_str=''):
    cfg=_cfg()
    if not candidates: return None, "no_candidates", {}
    # compute scores
    scores, why = score_arms(candidates, ripley_probs, dallas_scores, threshold, reasons_str=reasons_str)
    # argmax
    best = max(candidates, key=lambda a: scores.get(a,-1e12))
    # human "why now"
    parts=[]
    for k,v in (why.get(best) or []):
        parts.append(f"{k}={v:.3f}")
    why_text = "; ".join(parts) if parts else "blended"
    return best, why_text, {'scores': scores.get(best,0.0)}
