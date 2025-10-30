import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import Game from "../pages/Game";
import Settings from "../pages/Settings";

export default function AppRoutes() {
  return (
    <BrowserRouter>
      <header className="w-full border-b border-zinc-800 bg-zinc-900">
        <nav className="mx-auto flex max-w-5xl items-center gap-4 p-3">
          <div className="font-semibold">Nerdle Trainer</div>
          <NavLink to="/" end className="px-2 py-1 rounded hover:bg-zinc-800" >
            Game
          </NavLink>
          <NavLink to="/settings" className="px-2 py-1 rounded hover:bg-zinc-800">
            Settings
          </NavLink>
        </nav>
      </header>
      <main className="mx-auto max-w-5xl p-4">
        <Routes>
          <Route path="/" element={<Game />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
