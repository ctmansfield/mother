import { Routes, Route, NavLink, Navigate } from "react-router-dom";
import Home from "./pages/Home";
import Play from "./pages/Play";
import SettingsPage from "./pages/Settings";
import CoachPage from "./pages/Coach";
import { RequireSettings, RequireGame } from "./routes/guards";

export default function App() {
  return (
    <div className="min-h-dvh grid grid-rows-[auto,1fr]">
      <header className="sticky top-0 z-10 bg-neutral-950/80 backdrop-blur border-b border-neutral-800">
        <div className="mx-auto max-w-6xl px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="text-xl font-black">Nerdle Trainer</div>
          </div>
          <nav className="flex items-center gap-1 text-sm">
            <Tab to="/">Start</Tab>
            <Tab to="/play">Play</Tab>
            <Tab to="/coach">Coach</Tab>
            <Tab to="/settings">Settings</Tab>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl w-full px-4 py-6">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route
            path="/play"
            element={
              <RequireSettings>
                <RequireGame>
                  <Play />
                </RequireGame>
              </RequireSettings>
            }
          />
          <Route
            path="/coach"
            element={
              <RequireSettings>
                <RequireGame>
                  <CoachPage />
                </RequireGame>
              </RequireSettings>
            }
          />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

function Tab({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `px-3 py-1 rounded-lg ${
          isActive ? "bg-neutral-800" : "hover:bg-neutral-800/60"
        }`
      }
    >
      {children}
    </NavLink>
  );
}
