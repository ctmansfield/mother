import React, { useState } from "react";
import { useStore } from "../state/store";

export default function SettingsPage() {
  const { settings, setSettings, resetGame } = useStore();
  const [apiBase, setApiBase] = useState(settings.apiBase);
  const [length, setLength] = useState(settings.defaultLength);
  const [ops, setOps] = useState(settings.ops);

  function save() {
    setSettings({ apiBase, defaultLength: length, ops });
    resetGame();
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
      <div className="text-lg font-medium">Settings</div>
      <div className="grid sm:grid-cols-2 gap-6">
        <label className="block">
          <div className="text-sm mb-1">API Base</div>
          <input
            value={apiBase}
            onChange={(e) => setApiBase(e.target.value)}
            className="w-full bg-zinc-800 text-zinc-100 rounded px-3 py-2"
            placeholder="http://10.10.10.2:8082  or  /nerdle"
          />
          <div className="text-xs text-zinc-500 mt-1">Tip: keep “/nerdle” to use the dev proxy.</div>
        </label>

        <label className="block">
          <div className="text-sm mb-1">Default Length</div>
          <input
            type="number"
            min={5}
            max={12}
            value={length}
            onChange={(e) => setLength(Number(e.target.value))}
            className="w-full bg-zinc-800 text-zinc-100 rounded px-3 py-2"
          />
        </label>

        <label className="block">
          <div className="text-sm mb-1">Allowed Ops</div>
          <input
            value={ops}
            onChange={(e) => setOps(e.target.value)}
            className="w-full bg-zinc-800 text-zinc-100 rounded px-3 py-2"
            placeholder="+-*/="
          />
        </label>
      </div>

      <button
        onClick={save}
        className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-md"
      >
        Save & reset game
      </button>
    </div>
  );
}
