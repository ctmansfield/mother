# MOTHER — Metadata Bundle & Model Roadmap (Patch Pack A)

_Alien-verse theme; local, privacy-first. Generated on 20250924_193722._

## Naming Map
- **Nostromo**: Recommender (choose best nudge/context)
- **Lambert**: Content-based match (nudge ↔ state)
- **Dallas**: Self collaborative filtering (your successful past contexts)
- **Weyland**: Hybrid embeddings (context × nudge)
- **Ripley**: Propensity (P(action ≤ 30m))
- **Bishop**: Contextual bandit (time×tone×channel×category)
- **Hudson**: A/B & multivariate testing
- **LV-426**: Reinforcement learning (long-term habit reward)
- **Ash**: Uplift/causal incrementality
- **Vasquez**: Scheduling/survival (best send window)
- **Gorman**: Sequence/next-action modeling
- **Acheron**: Segmentation/clustering ("morning-you", "fatigued-you")
- **Xeno-Forge**: Creative optimization (LLM micro-copy)
- **Newt**: Guardrails (budgets/cooldowns/quiet hours)
- **Kane**: Explainability ("why-now")

## KPIs
- Nudge efficacy ↑, false-positives ↓, P95 latency <200ms eval/dispatch,
  ≤8 background wakeups/day, calibration (ECE ≤0.05), Qini uplift > 0.

## Feature (Metadata) Bundle v1
Context: hour, DOW, since_last_nudge, quiet_proximity, device_idle, calendar_busy, battery_state
Physiology: HR, HRV, RHRΔ, sleep mins/efficiency, steps, inactivity mins, readiness
History: adherence_7d/28d, streak_len, acted_≤10/30/60m, dismiss_7d, fatigue_index
Message: category, tone, length, has_number, has_emoji, channel, has_whynow, followup_chain
Ethics: med_restrictions, stress_trigger_present, budget_remaining

## Guardrails (Newt)
- Daily budget, per-category cooldowns, quiet hours, penalties for dismissals, opt-out respected.

## Acceptance Tests (high-level)
- Bandit ignores→cooldown; Propensity calibrated (ECE≤0.05);
  Uplift Qini>0; Quiet-hour violations=0; All alerts include a reason.

## Copy Banks (seed)
Hydration, Posture, Focus, Movement, Sleep, Breathing (≤18 words, single CTA, optional why-now).

## Rollout
Week 1: persist/debounce + quiet hours/budget + content packs
Week 2: bandit MVP + readiness + fixtures
Week 3: coalesced jobs + why-now + latency monitor
Week 4: telemetry (opt-in) + tuning
