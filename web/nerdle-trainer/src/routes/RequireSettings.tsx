import { ReactNode } from "react";
import { useSettingsStore } from "../state/settings.store";
import { Navigate } from "react-router-dom";

export function RequireSettings({ children }: { children: ReactNode }) {
  const ready = useSettingsStore(s => !!s.apiBase && s.length > 0 && s.ops.length > 0);
  return ready ? children : <Navigate to="/settings" replace />;
}
