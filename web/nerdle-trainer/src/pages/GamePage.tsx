import { useEffect, useMemo, useState } from "react";
import { useSettingsStore } from "../state/settings.store";

type StartResp = { game_id: string; status: string; length: number; attempts_used: number; max_attempts: number };
type GuessResp = {
  valid: boolean; reason?: string | null; tiles?: Array<{c:string; state:'absent'|'present'|'correct'}>|null;
  attempts_used: number; attempts_left: number; status: 'active'|'won'|'lost'; hint?: string|null
};

export function GamePage() {
  const st = useSettingsStore();
  const base = st.apiBase.endsWith("/nerdle") ? st.apiBase : st.apiBase.replace(/\/+$/,"") + "/nerdle";
  const [game, setGame] = useState<StartResp|null>(null);
  const [guess, setGuess] = useState("");
  const [last, setLast] = useState<GuessResp|null>(null);
  const [error, setError] = useState<string>("");

  async function start() {
    setError("");
    setLast(null);
    setGuess("");
    const body = { user_id: "u_dev", difficulty: "normal", length: st.length, ops: st.ops };
    const r = await fetch(base + "/start", { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify(body) });
    if (!r.ok) { setError(`Start failed: ${r.status}`); return; }
    const j = await r.json() as StartResp;
    setGame(j);
  }

  async function submit() {
    if (!game) return;
    const body = { user_id: "u_dev", game_id: (game as any).game_id, guess };
    const r = await fetch(base + "/guess", { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify(body) });
    const j = await r.json() as GuessResp;
    setLast(j);
    if (!j.valid && j.reason) setError(j.reason);
    else setError("");
  }

  useEffect(()=>{ if (!game) start(); },[]);

  // Very rough keyboard heatmap from last tiles
  const heat = useMemo(()=>{
    const m: Record<string, number> = {};
    (last?.tiles||[]).forEach(t=>{
      m[t.c] = Math.max(m[t.c]||0, t.state === 'correct' ? 3 : t.state === 'present' ? 2 : 1);
    });
    return m;
  }, [last]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button className="btn" onClick={start}>New Game</button>
        <span className="text-sm text-zinc-400">Length: {game?.length ?? st.length} • Ops: {st.ops}</span>
      </div>

      <div className="grid gap-3 max-w-xl">
        <input
          className="input text-lg tracking-widest"
          placeholder={`Type a ${game?.length ?? st.length}-char equation (e.g. 12+3*4=24)`}
          value={guess}
          onChange={e=>setGuess(e.target.value)}
        />
        <div className="flex gap-2">
          <button className="btn-primary" onClick={submit} disabled={!game}>Guess</button>
        </div>
        {error && <p className="text-red-400 text-sm">{error}</p>}
      </div>

      <TilesGrid tiles={last?.tiles||[]} />

      <section className="grid md:grid-cols-2 gap-6">
        <KeyboardHeatmap heat={heat} />
        <ConstraintVisualizer guess={guess} tiles={last?.tiles||[]} />
      </section>

      <style>{styles}</style>
    </div>
  );
}

function TilesGrid({ tiles }:{ tiles: Array<{c:string; state:string}> }) {
  if (!tiles?.length) return null;
  return (
    <div className="flex gap-1">
      {tiles.map((t, i)=>(
        <div key={i} className={"tile " + t.state}>{t.c}</div>
      ))}
    </div>
  );
}

function KeyboardHeatmap({ heat }:{ heat: Record<string, number> }) {
  const keys = "1234567890+-*/=".split("");
  return (
    <div>
      <h3 className="text-sm text-zinc-400 mb-2">Keyboard heat</h3>
      <div className="grid grid-cols-8 gap-1">
        {keys.map(k=>{
          const lvl = heat[k]||0;
          return <div key={k} className={"k " + lvl}>{k}</div>;
        })}
      </div>
    </div>
  );
}

function ConstraintVisualizer({ guess, tiles }:{ guess:string; tiles:Array<{c:string; state:string}> }) {
  const must = new Set<string>();
  const cant = new Set<string>();
  const fixed: Record<number,string> = {};
  tiles?.forEach((t,i)=>{
    if (t.state === "present") must.add(t.c);
    if (t.state === "absent")  cant.add(t.c);
    if (t.state === "correct") fixed[i] = t.c;
  });
  return (
    <div>
      <h3 className="text-sm text-zinc-400 mb-2">Constraints</h3>
      <div className="grid gap-2 text-sm">
        <Row label="Must have" value={[...must].join(" ")} />
        <Row label="Cannot have" value={[...cant].join(" ")} />
        <Row label="Fixed positions" value={
          Object.keys(fixed).length ? Object.entries(fixed).map(([i,c])=>`${i}:${c}`).join(" ")
          : "(none)"
        } />
      </div>
    </div>
  );
}

function Row({label, value}:{label:string; value:string}) {
  return (
    <div className="flex gap-2">
      <div className="w-32 text-zinc-400">{label}</div>
      <div className="font-mono">{value}</div>
    </div>
  );
}

const styles = `
.input{ @apply px-3 py-2 rounded-md bg-zinc-900 border border-zinc-800 outline-none focus:border-zinc-600; }
.btn{ @apply px-3 py-2 rounded-md bg-zinc-800 hover:bg-zinc-700; }
.btn-primary{ @apply px-3 py-2 rounded-md bg-indigo-600 hover:bg-indigo-500; }
.tile{ @apply w-10 h-10 grid place-items-center rounded-md font-mono border border-zinc-800; }
.tile.absent{ @apply bg-zinc-900; }
.tile.present{ @apply bg-yellow-600/40; }
.tile.correct{ @apply bg-green-600/40; }
.k{ @apply px-2 py-1 rounded-md border border-zinc-800 text-center; }
.k.1{ @apply bg-zinc-900; }
.k.2{ @apply bg-yellow-600/40; }
.k.3{ @apply bg-green-600/40; }
`;
