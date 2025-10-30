import { FormEvent, useState } from "react";
import { api } from "../services/api";
import { useGame } from "../state/GameContext";
import { useSettings } from "../state/SettingsContext";
import { useNavigate } from "react-router-dom";
export default function Home(){
  const { settings } = useSettings();
  const { dispatch } = useGame();
  const [userId,setUserId]=useState("u_player");
  const [length,setLength]=useState<number>(settings.defaultLength);
  const [difficulty,setDifficulty]=useState("normal");
  const [ops,setOps]=useState(settings.ops);
  const [busy,setBusy]=useState(false);
  const [err,setErr]=useState<string|null>(null);
  const nav=useNavigate();
  async function start(e:FormEvent){
    e.preventDefault(); setBusy(true); setErr(null);
    try{
      const res = await api.start({ user_id:userId, difficulty, length, ops });
      dispatch({ type:"NEW_GAME", game:{ gameId:res.game_id, userId, length:res.length, maxAttempts:res.max_attempts, attemptsUsed:res.attempts_used, status:res.status } });
      nav("/play");
    }catch(e:any){ setErr(e.message); } finally{ setBusy(false); }
  }
  return (
    <div className="grid md:grid-cols-2 gap-6">
      <form onSubmit={start} className="bg-neutral-900 rounded-2xl p-5 shadow-soft grid gap-4">
        <div className="text-lg font-semibold">Start a game</div>
        <div className="grid grid-cols-2 gap-3">
          <L label="User ID"><input className="w-full bg-neutral-800 rounded-lg px-3 py-2" value={userId} onChange={e=>setUserId(e.target.value)} /></L>
          <L label="Difficulty"><select className="w-full bg-neutral-800 rounded-lg px-3 py-2" value={difficulty} onChange={e=>setDifficulty(e.target.value)}><option value="normal">normal</option><option value="hard">hard</option></select></L>
          <L label="Length"><input type="number" min={6} max={12} className="w-full bg-neutral-800 rounded-lg px-3 py-2" value={length} onChange={e=>setLength(Number(e.target.value))} /></L>
          <L label="Operators"><input className="w-full bg-neutral-800 rounded-lg px-3 py-2" value={ops} onChange={e=>setOps(e.target.value)} /></L>
        </div>
        <div className="flex gap-2"><button className="button" disabled={busy}>{busy?"Starting...":"Start"}</button>{err && <div className="text-red-400 text-sm">{err}</div>}</div>
      </form>
      <div className="bg-neutral-900 rounded-2xl p-5 shadow-soft grid gap-3">
        <div className="text-lg font-semibold">How it works</div>
        <ul className="text-sm list-disc list-inside text-neutral-300 grid gap-1">
          <li>Start a game, then enter guesses in the Play tab.</li>
          <li>Use “Hint” for a nudge or “Coach me” for constraints + a probe guess.</li>
          <li>Settings let you change API base, default length, and allowed operators.</li>
        </ul>
        <div className="text-xs text-neutral-500">API base: <span className="font-mono">{settings.apiBase}</span></div>
      </div>
    </div>
  );
}
function L({ label, children }: { label:string; children:React.ReactNode }){ return (<label className="grid gap-1"><span className="text-xs uppercase text-neutral-400">{label}</span>{children}</label>); }
