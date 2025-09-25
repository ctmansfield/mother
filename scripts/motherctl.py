#!/usr/bin/env python3
# motherctl: select/explain/diagnose/feedback with Hudson, Vasquez, Ash, Bishop (beta|contextual|linucb|thompson)
import os
import json
import argparse
import random
import time
import sys
import math
from datetime import datetime, timedelta

STATE_PATH = os.path.join("out", "bishop_state.json")
NUDGES_LOG = os.path.join("out", "nudges.csv")
NEWT_STATE_PATH = os.path.join("out", "newt_state.json")

# Bandits & Ripley fast path (imports live at module top)
from scripts.bishop_ctx import CtxBandit, feat_vec_from_arm as ctx_feat

import scripts.ripley_fast as ripley


def ensure_out():
    os.makedirs("out", exist_ok=True)
    if not os.path.exists(NUDGES_LOG):
        with open(NUDGES_LOG, "w") as f:
            f.write("ts,arm,reward\n")
    if not os.path.exists(os.path.join("out", "ash_log.csv")):
        with open(os.path.join("out", "ash_log.csv"), "w") as f:
            f.write("ts,arm,category,daypart,tone,channel,treatment,p,reason\n")


def load_yaml(path):
    try:
        import yaml

        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def load_policy():
    pol = load_yaml(os.path.join("content", "policy.yaml")) or {}
    return pol.get("policy") or {
        "budget_per_day": 6,
        "cooldowns": {
            "hydration": "90m",
            "posture": "120m",
            "movement": "60m",
            "focus": "60m",
            "sleep": "180m",
        },
        "quiet_hours": ["22:00-07:00"],
        "send_threshold": 0.28,
        "penalty_dismiss": 0.2,
    }


def load_feedback_policy():
    fb = load_yaml(os.path.join("content", "feedback_policy.yaml")) or {}
    fb = fb.get("feedback") if isinstance(fb, dict) else None
    return fb or {
        "ignore_to_escalate": 3,
        "escalate_duration": "6h",
        "decay_period": "24h",
    }


def load_weights():
    w = load_yaml(os.path.join("content", "propensity_weights.yaml")) or {}
    return (w.get("weights") if isinstance(w, dict) else None) or {"bias": -0.5}


def parse_secs(s: str) -> int:
    if not s:
        return 0
    s = s.strip().lower()
    if s.endswith("ms"):
        return max(int(float(s[:-2]) / 1000.0), 0)
    if s.endswith("s"):
        return int(float(s[:-1]))
    if s.endswith("m"):
        return int(float(s[:-1]) * 60)
    if s.endswith("h"):
        return int(float(s[:-1]) * 3600)
    if s.endswith("d"):
        return int(float(s[:-1]) * 86400)
    return int(float(s))


def in_quiet(quiet_spans, now: datetime):
    t = now.time()
    for span in quiet_spans or []:
        try:
            start, end = span.split("-")
            hs, ms = map(int, start.split(":"))
            he, me = map(int, end.split(":"))
            s = datetime.combine(now.date(), datetime.min.time()).replace(
                hour=hs, minute=ms
            )
            e = datetime.combine(now.date(), datetime.min.time()).replace(
                hour=he, minute=me
            )
            if s <= e:
                if s.time() <= t <= e.time():
                    return True
            else:
                if t >= s.time() or t <= e.time():
                    return True
        except Exception:
            continue
    return False


def load_newt_state():
    st = {
        "date": datetime.now().date().isoformat(),
        "sent_today": 0,
        "last_sent": {},
        "neg": {},
        "esc": {},
    }
    if os.path.exists(NEWT_STATE_PATH):
        try:
            existing = json.load(open(NEWT_STATE_PATH))
            for k, v in existing.items():
                st[k] = v
            st.setdefault("neg", {})
            st.setdefault("esc", {})
        except Exception:
            pass
    return st


def save_newt_state(st):
    os.makedirs(os.path.dirname(NEWT_STATE_PATH), exist_ok=True)
    json.dump(st, open(NEWT_STATE_PATH, "w"))


def cooldown_remaining(policy_cfg, category, now, st):
    last_iso = (st.get("last_sent") or {}).get(category)
    base = 0
    if last_iso:
        try:
            last = datetime.fromisoformat(last_iso)
            cd = (policy_cfg.get("cooldowns") or {}).get(category)
            if cd:
                rem = parse_secs(cd) - (now - last).total_seconds()
                base = int(rem) if rem > 0 else 0
        except Exception:
            pass
    esc_until = (st.get("esc") or {}).get(category)
    extra = 0
    if esc_until:
        try:
            until = datetime.fromisoformat(esc_until)
            rem = (until - now).total_seconds()
            extra = int(rem) if rem > 0 else 0
        except Exception:
            pass
    return base, extra


def newt_allow_persistent(
    policy_cfg: dict, category: str, now: datetime, dry_run=False
):
    st = load_newt_state()
    today = now.date().isoformat()
    if st.get("date") != today:
        st["date"] = today
        st["sent_today"] = 0
    base_rem, esc_rem = cooldown_remaining(policy_cfg, category, now, st)
    if esc_rem > 0:
        return False, "escalated", st
    if st.get("sent_today", 0) >= int(policy_cfg.get("budget_per_day", 6)):
        return False, "budget", st
    if base_rem > 0:
        return False, "cooldown", st
    if in_quiet(policy_cfg.get("quiet_hours"), now):
        return False, "quiet", st
    if not dry_run:
        st["sent_today"] = int(st.get("sent_today", 0)) + 1
        st.setdefault("last_sent", {})[category] = now.isoformat()
        save_newt_state(st)
    return True, "ok", st


def record_feedback(policy_cfg, fb_cfg, category, reward, now):
    st = load_newt_state()
    if int(reward) == 0:
        neg = st.setdefault("neg", {}).get(category, {"count": 0, "last": None})
        last_ts = None
        if neg.get("last"):
            try:
                last_ts = datetime.fromisoformat(neg["last"])
            except Exception:
                last_ts = None
        if (last_ts is None) or (
            (now - last_ts).total_seconds()
            > parse_secs(fb_cfg.get("decay_period", "24h"))
        ):
            neg = {"count": 0, "last": None}
        neg["count"] = int(neg.get("count", 0)) + 1
        neg["last"] = now.isoformat()
        st.setdefault("neg", {})[category] = neg
        if neg["count"] >= int(fb_cfg.get("ignore_to_escalate", 3)):
            dur = parse_secs(fb_cfg.get("escalate_duration", "6h"))
            until = now + timedelta(seconds=dur)
            st.setdefault("esc", {})[category] = until.isoformat()
            neg["count"] = 0
        save_newt_state(st)
    else:
        st.setdefault("neg", {}).pop(category, None)
        save_newt_state(st)


def arm_features(arm: str):
    parts = (arm or "").split("|")
    dp, tone, ch, cat = (parts + [None, None, None, None])[:4]
    x = {"bias": 1.0}
    if dp:
        x[f"daypart_{dp}"] = 1.0
    if tone:
        x[f"tone_{tone}"] = 1.0
    if ch:
        x[f"channel_{ch}"] = 1.0
    if cat:
        x[f"category_{cat}"] = 1.0
    return x


def dot(weights: dict, x: dict):
    return sum(float(weights.get(k, 0.0)) * float(v) for k, v in x.items())


def sigmoid(z: float):
    try:
        return 1.0 / (1.0 + math.exp(-z))
    except Exception:
        return 0.5


class BetaArm:
    def __init__(self, a=1.0, b=1.0):
        self.a, self.b = a, b

    def sample(self):
        x = random.gammavariate(self.a, 1.0)
        y = random.gammavariate(self.b, 1.0)
        return x / (x + y) if (x + y) > 0 else 0.5

    def update(self, r):
        self.a += r
        self.b += 1 - r


class BanditState:
    def __init__(self, path=STATE_PATH):
        self.path = path
        self.arms = {}
        if os.path.exists(path):
            try:
                raw = json.load(open(path))
                self.arms = {
                    k: BetaArm(v.get("a", 1.0), v.get("b", 1.0)) for k, v in raw.items()
                }
            except Exception:
                self.arms = {}

    def to_dict(self):
        return {k: {"a": v.a, "b": v.b} for k, v in self.arms.items()}

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        json.dump(self.to_dict(), open(self.path, "w"))

    def ensure_arm(self, arm):
        if arm not in self.arms:
            self.arms[arm] = BetaArm()


# Vasquez
def load_vasquez_windows():
    v = load_yaml(os.path.join("content", "vasquez_windows.yaml")) or {}
    return v.get("vasquez_windows") or {}


def vasquez_allowed(category, now):
    vw = load_vasquez_windows()
    by = vw.get("by_category") or {}
    hours = (by.get(category) or {}).get("hours") or []
    hour = now.hour
    ok = hour in set(int(h) for h in hours)
    nxt = None
    if hours:
        for i in range(1, 25):
            hh = (hour + i) % 24
            if hh in hours:
                nxt = hh
                break
    wait = None
    if nxt is not None:
        delta = (nxt - hour) % 24
        wait = int(delta * 3600)
    return ok, nxt, wait, hours


# Hudson (optional)
try:
    import hudson
except Exception:
    hudson = None


# Ash
def load_ash_cfg():
    a = load_yaml(os.path.join("content", "ash.yaml")) or {}
    return a.get("ash") or {}


def load_ash_table():
    a = load_yaml(os.path.join("content", "ash_table.yaml")) or {}
    return a.get("ash_table") or {}


def load_ash_tau():
    a = load_yaml(os.path.join("content", "ash_tau.yaml")) or {}
    a = a.get("ash_tau") or {}
    return a.get("tau_by_category") or {}


def ash_key_parts(arm):
    parts = (arm or "").split("|")
    return {
        "daypart": parts[0] if len(parts) > 0 else "",
        "tone": parts[1] if len(parts) > 1 else "",
        "channel": parts[2] if len(parts) > 2 else "",
        "category": parts[3] if len(parts) > 3 else "",
    }


def ash_estimate_uplift(arm):
    tab = load_ash_table()
    upl = tab.get("uplift", {}) or {}
    p = ash_key_parts(arm)
    keys = [
        f"{p['category']}|{p['daypart']}|{p['tone']}|{p['channel']}",
        f"{p['category']}|{p['daypart']}|{p['tone']}|*",
        f"{p['category']}|{p['daypart']}|*|*",
        f"{p['category']}|*|*|*",
        "*|*|*|*",
    ]
    for k in keys:
        if k in upl:
            return float(upl[k])
    return float(tab.get("default", 0.01))


def ash_log_exposure(ts, arm, category, daypart, tone, channel, treatment, p, reason):
    path = os.path.join("out", "ash_log.csv")
    with open(path, "a") as f:
        f.write(
            f"{ts},{arm},{category},{daypart},{tone},{channel},{int(treatment)},{p:.4f},{reason}\n"
        )


def score_arm(weights, arm):
    x = {"bias": 1.0}
    parts = (arm or "").split("|")
    if len(parts) > 0:
        x[f"daypart_{parts[0]}"] = 1.0
    if len(parts) > 1:
        x[f"tone_{parts[1]}"] = 1.0
    if len(parts) > 2:
        x[f"channel_{parts[2]}"] = 1.0
    if len(parts) > 3:
        x[f"category_{parts[3]}"] = 1.0
    z = dot(load_weights(), x)
    p = sigmoid(z)
    return p, z


def main():
    ap = argparse.ArgumentParser(description="motherctl")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser(
        "select",
        help="choose a nudge; supports grid; uplift gating; holdout; contextual/linucb/thompson",
    )
    sp.add_argument(
        "--category",
        default="hydration",
        choices=["hydration", "posture", "movement", "focus", "sleep"],
    )
    sp.add_argument(
        "--tone", default="auto", choices=["auto", "gentle", "humor", "strict"]
    )
    sp.add_argument("--channel", default="auto", choices=["auto", "push", "in_app"])
    sp.add_argument("--reasons", "--why-now", dest="reasons", default="")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument(
        "--grid-tones", default="", help="comma list: e.g., gentle,humor,strict"
    )
    sp.add_argument("--grid-channels", default="", help="comma list: e.g., push,in_app")
    sp.add_argument("--k", type=int, default=3)
    sp.add_argument("--exp-off", action="store_true")
    sp.add_argument("--vasquez-off", action="store_true")
    sp.add_argument("--ash-off", action="store_true")
    sp.add_argument(
        "--bandit", default="beta", choices=["beta", "contextual", "linucb", "thompson"]
    )

    xp = sub.add_parser("explain")
    xp.add_argument("--arm")
    xp.add_argument(
        "--category",
        default="hydration",
        choices=["hydration", "posture", "movement", "focus", "sleep"],
    )
    xp.add_argument("--tone", default="gentle", choices=["gentle", "humor", "strict"])
    xp.add_argument("--channel", default="push", choices=["push", "in_app"])
    xp.add_argument("--hour", type=int)

    dx = sub.add_parser("diagnose")
    dx.add_argument(
        "--category",
        default="hydration",
        choices=["hydration", "posture", "movement", "focus", "sleep"],
    )
    dx.add_argument("--tone", default="gentle", choices=["gentle", "humor", "strict"])
    dx.add_argument("--channel", default="push", choices=["push", "in_app"])
    dx.add_argument("--hour", type=int)

    fp = sub.add_parser("feedback")
    fp.add_argument("--arm", required=True)
    fp.add_argument("--reward", type=int, choices=[0, 1])
    fp.add_argument("--dismiss", action="store_true")

    args = ap.parse_args()
    ensure_out()

    if args.cmd == "select":
        now = datetime.now()
        hour = now.hour
        pol = load_policy()
        daypart = (
            "morning"
            if 6 <= hour < 11
            else (
                "midday"
                if 11 <= hour < 14
                else ("afternoon" if 14 <= hour < 18 else "evening")
            )
        )
        tones = (
            [t.strip() for t in args.grid_tones.split(",") if t.strip()]
            if args.grid_tones
            else None
        )
        channels = (
            [c.strip() for c in args.grid_channels.split(",") if c.strip()]
            if args.grid_channels
            else None
        )
        tone = args.tone if args.tone != "auto" else "gentle"
        channel = args.channel if args.channel != "auto" else "push"
        category = args.category
        threshold = float(pol.get("send_threshold", 0.28))
        templates = (
            load_yaml(os.path.join("content", "templates", "reminders.yaml")) or {}
        )
        tau_map = load_ash_tau()
        ash_cfg = load_ash_cfg()
        tau = float(tau_map.get(category, ash_cfg.get("tau", 0.01)))

        # Hudson (optional)
        if (not args.exp_off) and (hudson is not None):
            try:
                exp, var_key, var_meta = hudson.choose_for_category(category, now)
                if exp and var_meta:
                    tone = var_meta.get("tone", tone)
                    channel = var_meta.get("channel", channel)
            except Exception:
                pass

        # Vasquez gating
        if not args.vasquez_off:
            ok_v, nxt_h, wait_s, hours = vasquez_allowed(category, now)
            if not ok_v:
                print(
                    json.dumps(
                        {
                            "allowed": False,
                            "reason": "vasquez_window",
                            "ts": int(time.time()),
                            "arm": f"{daypart}|{tone}|{channel}|{category}",
                            "category": category,
                            "allowed_hours": hours,
                            "next_hour": nxt_h,
                            "wait_s": wait_s,
                        },
                        ensure_ascii=False,
                    )
                )
                sys.exit(0)

        # Guardrails (dry run check)
        ok, reason, st = newt_allow_persistent(pol, category, now, dry_run=True)
        if not ok:
            base_rem, esc_rem = cooldown_remaining(pol, category, now, st)
            print(
                json.dumps(
                    {
                        "allowed": False,
                        "reason": reason,
                        "ts": int(time.time()),
                        "category": category,
                        "threshold": threshold,
                        "cooldown_remaining_s": base_rem,
                        "escalated_remaining_s": esc_rem,
                        "budget_remaining": max(
                            int(pol.get("budget_per_day", 6))
                            - int(st.get("sent_today", 0)),
                            0,
                        ),
                    },
                    ensure_ascii=False,
                )
            )
            sys.exit(0)

        # Build candidate grid (all bandits use the same candidates)
        tones = tones or ["gentle", "humor", "strict"]
        channels = channels or ["push", "in_app"]
        candidates = [f"{daypart}|{t}|{c}|{category}" for t in tones for c in channels]

        choice = None
        if args.bandit == "beta":
            try:
                scored = ripley.batch_score(candidates)
                choice = scored[0][0] if scored else None
                # Nostromo blend (override choice unless --nostromo-off)
                if not args.nostromo_off:
                    try:
                        choice_n, why_n, meta_n = nostromo.pick(
                            candidates,
                            threshold,
                            dallas_scores,
                            ripley_probs,
                            getattr(args, "reasons", ""),
                        )
                        if choice_n:
                            choice = choice_n
                            why_now = (
                                (why_now + "; " + why_n)
                                if "why_now" in locals() and why_now
                                else why_n
                            )
                    except Exception:
                        pass
            except Exception:
                # fallback single-score path
                scored = []
                for arm in candidates:
                    p, _ = score_arm(load_weights(), arm)
                    scored.append((arm, p))
                scored.sort(key=lambda t: t[1], reverse=True)
                choice = scored[0][0] if scored else None
                # Nostromo blend (override choice unless --nostromo-off)
                if not args.nostromo_off:
                    try:
                        choice_n, why_n, meta_n = nostromo.pick(
                            candidates,
                            threshold,
                            dallas_scores,
                            ripley_probs,
                            getattr(args, "reasons", ""),
                        )
                        if choice_n:
                            choice = choice_n
                            why_now = (
                                (why_now + "; " + why_n)
                                if "why_now" in locals() and why_now
                                else why_n
                            )
                    except Exception:
                        pass
        elif args.bandit == "contextual":
            ctx = CtxBandit()
            choice = ctx.choose(candidates)
        elif args.bandit == "linucb":
            ctx = LinUCBBandit()
            choice = ctx.choose(candidates)
        elif args.bandit == "thompson":
            ctx = ThompsonBandit()
            choice = ctx.choose(candidates)

        p, _ = score_arm(load_weights(), choice)
        if p < threshold:
            print(
                json.dumps(
                    {
                        "allowed": False,
                        "reason": "below_threshold",
                        "ts": int(time.time()),
                        "arm": choice,
                        "category": category,
                        "p": round(p, 4),
                        "threshold": threshold,
                    },
                    ensure_ascii=False,
                )
            )
            sys.exit(0)
        if not args.ash_off:
            up = float(ash_estimate_uplift(choice))
            if up < tau:
                ts = int(time.time())
                parts = choice.split("|")
                ash_log_exposure(
                    ts,
                    choice,
                    category,
                    parts[0],
                    parts[1],
                    parts[2],
                    0,
                    p,
                    "low_uplift",
                )
                print(
                    json.dumps(
                        {
                            "allowed": False,
                            "reason": "ash_low_uplift",
                            "arm": choice,
                            "uplift": round(up, 4),
                            "tau": tau,
                        },
                        ensure_ascii=False,
                    )
                )
                sys.exit(0)

        txts = templates.get(category) or ["Do a tiny reset."]
        out = {
            "allowed": True,
            "ts": int(time.time()),
            "arm": choice,
            "category": category,
            "text": random.choice(txts),
            "p": round(p, 4),
            "threshold": threshold,
            "why_now": f"{daypart} slot; p={p:.2f} (≥ {threshold:.2f})",
        }
        print(json.dumps(out, ensure_ascii=False))
        # Record exposure if not dry-run
        if not args.dry_run:
            newt_allow_persistent(pol, category, now, dry_run=False)
            with open(NUDGES_LOG, "a") as f:
                f.write(f"{out['ts']},{choice},\n")
            parts = choice.split("|")
            ash_log_exposure(
                out["ts"],
                choice,
                category,
                parts[0],
                parts[1],
                parts[2],
                1,
                out.get("p", 0.0),
                "send",
            )
        sys.exit(0)

    if args.cmd == "explain":
        if args.arm:
            arm = args.arm
        else:
            h = args.hour if args.hour is not None else datetime.now().hour
            arm = f"{('morning' if 6<=h<11 else ('midday' if 11<=h<14 else ('afternoon' if 14<=h<18 else 'evening')))}|{args.tone}|{args.channel}|{args.category}"
        w = load_weights()
        x = {"bias": 1.0}
        parts = arm.split("|")
        if len(parts) > 0:
            x[f"daypart_{parts[0]}"] = 1.0
        if len(parts) > 1:
            x[f"tone_{parts[1]}"] = 1.0
        if len(parts) > 2:
            x[f"channel_{parts[2]}"] = 1.0
        if len(parts) > 3:
            x[f"category_{parts[3]}"] = 1.0
        z = dot(w, x)
        p = sigmoid(z)
        contrib = {
            k: round(w.get(k, 0.0) * x.get(k, 0.0), 4)
            for k in sorted(
                x.keys(), key=lambda kk: -abs(w.get(kk, 0.0) * x.get(kk, 0.0))
            )
        }
        print(
            json.dumps(
                {"arm": arm, "z": round(z, 4), "p": round(p, 4), "contrib": contrib},
                ensure_ascii=False,
            )
        )
        sys.exit(0)

    if args.cmd == "diagnose":
        h = args.hour if args.hour is not None else datetime.now().hour
        arm = f"{('morning' if 6<=h<11 else ('midday' if 11<=h<14 else ('afternoon' if 14<=h<18 else 'evening')))}|{args.tone}|{args.channel}|{args.category}"
        pol = load_policy()
        now = datetime.now()
        st = load_newt_state()
        base_rem, esc_rem = cooldown_remaining(pol, args.category, now, st)
        w = load_weights()
        x = arm_features(arm)
        z = dot(w, x)
        p = sigmoid(z)
        tau = float(load_ash_tau().get(args.category, load_ash_cfg().get("tau", 0.01)))
        upl = ash_estimate_uplift(arm)
        print(
            json.dumps(
                {
                    "arm": arm,
                    "quiet_hours": in_quiet(pol.get("quiet_hours"), now),
                    "budget_remaining": max(
                        int(pol.get("budget_per_day", 6))
                        - int(st.get("sent_today", 0)),
                        0,
                    ),
                    "cooldown_remaining_s": base_rem,
                    "escalated_remaining_s": esc_rem,
                    "p": round(p, 4),
                    "threshold": float(pol.get("send_threshold", 0.28)),
                    "uplift": round(float(upl), 4),
                    "uplift_tau": tau,
                },
                ensure_ascii=False,
            )
        )
        sys.exit(0)

    if args.cmd == "feedback":
        if args.dismiss and args.reward is None:
            args.reward = 0
        if args.reward is None:
            print(
                json.dumps(
                    {"error": "provide --reward 0|1 or --dismiss"}, ensure_ascii=False
                )
            )
            sys.exit(0)
        # Beta update
        st = BanditState()
        st.ensure_arm(args.arm)
        st.arms[args.arm].update(float(args.reward))
        st.save()
        # Contextual update
        try:
            ctx = CtxBandit()
            ctx.update(ctx_feat(args.arm), int(args.reward))
            ctx.save()
        except Exception:
            pass
        # LinUCB update
        try:
            l = LinUCBBandit()
            l.update(args.arm, int(args.reward))
            l.save()
        except Exception:
            pass
        # Thompson update
        try:
            t = ThompsonBandit()
            t.update(args.arm, int(args.reward))
            t.save()
        except Exception:
            pass
        pol = load_policy()
        fb = load_feedback_policy()
        cat = args.arm.split("|")[-1] if "|" in args.arm else "hydration"
        record_feedback(pol, fb, cat, args.reward, datetime.now())
        with open(NUDGES_LOG, "a") as f:
            f.write(f"{int(time.time())},{args.arm},{int(args.reward)}\n")
        print(json.dumps({"updated": args.arm, "reward": int(args.reward)}))
        sys.exit(0)


if __name__ == "__main__":
    main()
