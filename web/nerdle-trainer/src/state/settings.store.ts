import { create } from "zustand";

type Settings = {
  apiBase: string;
  length: number;
  ops: string;
};

type Store = Settings & {
  setAll: (s: Partial<Settings>) => void;
  reset: () => void;
};

const DEFAULTS: Settings = {
  apiBase: (import.meta.env.VITE_API_BASE as string) || "/nerdle",
  length: 8,
  ops: "+-*/="
};

const KEY = "nerdle:settings";

function load(): Settings {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    const obj = JSON.parse(raw);
    return { ...DEFAULTS, ...obj };
  } catch {
    return DEFAULTS;
  }
}

export const useSettingsStore = create<Store>((set, get) => ({
  ...load(),
  setAll: (s) => {
    const next = { ...get(), ...s };
    set(next);
    try { localStorage.setItem(KEY, JSON.stringify(next)); } catch {}
  },
  reset: () => {
    set(DEFAULTS);
    try { localStorage.setItem(KEY, JSON.stringify(DEFAULTS)); } catch {}
  }
}));
