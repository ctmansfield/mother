import React, { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { useStore } from "../state/store";
import { api, setApiBase } from "../services/api";
export function RequireGame({ children }: { children: React.ReactNode }) {
  const { settings, game, startGame } = useStore();
  const [ok, setOk] = useState<boolean | null>(null);

  useEffect(() => {
    (async () => {
setApiBase(settings.apiBase);
  const client = api;
      const healthy = await client.health().catch(() => false);
      setOk(healthy);
      if (healthy && !game.gameId) await startGame();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (ok === null) {
    return <div className="max-w-5xl mx-auto p-4 text-zinc-400">Checking server…</div>;
  }
  if (!ok) return <Navigate to="/settings" replace />;

  return <>{children}</>;
}
