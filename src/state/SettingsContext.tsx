import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

type Settings = {
  apiBase: string; // e.g. http://127.0.0.1:8082
  defaultLength: number;
  ops: string; // e.g. "+-*/="
};

const SETTINGS_KEY = "nerdle.settings.v1";

const SettingsCtx = createContext<{
  settings: Settings;
  setSettings: (s: Settings) => void;
}>({
  settings: { apiBase: "", defaultLength: 8, ops: "+-*/=" },
  setSettings: () => {},
});

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettingsState] = useState<Settings>(() => {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) return JSON.parse(raw);
    return {
      apiBase: window.location.origin, // same-origin by default
      defaultLength: 8,
      ops: "+-*/=",
    };
  });

  const setSettings = (s: Settings) => {
    setSettingsState(s);
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
  };

  const value = useMemo(() => ({ settings, setSettings }), [settings]);
  return <SettingsCtx.Provider value={value}>{children}</SettingsCtx.Provider>;
}

export function useSettings() {
  return useContext(SettingsCtx);
}

export function getSettings() {
  // for non-react callers
  const raw = localStorage.getItem(SETTINGS_KEY);
  return raw
    ? (JSON.parse(raw) as { apiBase: string; defaultLength: number; ops: string })
    : { apiBase: window.location.origin, defaultLength: 8, ops: "+-*/=" };
}
