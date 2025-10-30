import { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useSettings } from "../state/SettingsContext";
import { useGame } from "../state/GameContext";

export function RequireSettings({ children }: { children: ReactNode }) {
  const { settings } = useSettings();
  const loc = useLocation();
  if (!settings.apiBase) {
    return <Navigate to="/settings" replace state={{ from: loc }} />;
  }
  return <>{children}</>;
}

export function RequireGame({ children }: { children: ReactNode }) {
  const { state } = useGame();
  const loc = useLocation();
  if (!state.game) {
    return <Navigate to="/" replace state={{ from: loc }} />;
  }
  return <>{children}</>;
}
