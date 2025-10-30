import React from "react";
import { NavLink } from "react-router-dom";

export function Nav() {
  return (
    <div className="border-b border-zinc-800">
      <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-6">
        <div className="font-semibold">Nerdle Trainer</div>
        <NavLink to="/" className={({ isActive }) => (isActive ? "px-2 py-1 rounded bg-zinc-800" : "px-2 py-1 rounded")}>
          Game
        </NavLink>
        <NavLink to="/settings" className={({ isActive }) => (isActive ? "px-2 py-1 rounded bg-zinc-800" : "px-2 py-1 rounded")}>
          Settings
        </NavLink>
      </div>
    </div>
  );
}
