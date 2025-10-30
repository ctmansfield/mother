import { Link, Outlet, useLocation } from "react-router-dom";

export function AppLayout() {
  const { pathname } = useLocation();
  return (
    <div className="min-h-dvh flex flex-col">
      <header className="border-b border-zinc-800">
        <nav className="mx-auto max-w-5xl px-4 py-3 flex items-center gap-4">
          <h1 className="font-semibold text-lg tracking-wide">Nerdle Trainer</h1>
          <Link className={navClass(pathname === "/")} to="/">Game</Link>
          <Link className={navClass(pathname === "/settings")} to="/settings">Settings</Link>
        </nav>
      </header>
      <main className="mx-auto max-w-5xl w-full px-4 py-6 flex-1">
        <Outlet />
      </main>
      <footer className="text-xs text-zinc-500 mx-auto max-w-5xl px-4 py-4">
        API: <code className="px-1 rounded bg-zinc-900 border border-zinc-800">
          {import.meta.env.VITE_API_BASE || "/nerdle"}
        </code>
      </footer>
    </div>
  );
}

function navClass(active: boolean) {
  return "px-3 py-1 rounded-md " + (active ? "bg-zinc-800" : "hover:bg-zinc-900");
}
