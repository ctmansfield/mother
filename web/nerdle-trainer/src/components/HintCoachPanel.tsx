import { useState } from "react";
import { api } from "../services/api";
import { useGame } from "../state/GameContext";
export default function HintCoachPanel(){
  const { state, dispatch } = useGame();
  const [busy,setBusy]=useState(false);
  const [hint,setHint]=useState<string|null>(null);
  const can=!!state.game;
  async function ask(kind:"position"|"operator"){
    if(!state.game) return; setBusy(true);
    try{ const res=await api.hint({ game_id: state.game.gameId, user_id: state.game.userId, kind }); setHint(res.hint ?? null); }
    catch(e:any){ setHint(e.message); }
    finally{ setBusy(false); }
  }
  async function coach(){
    if(!state.game) return; setBusy(true);
    try{
      const res=await api.coach(state.game.gameId, state.game.userId);
      dispatch({ type:"UPDATE_CONSTRAINTS", constraints: res.constraints });
      setHint([...(res.tips ?? []), res.probe ? `Suggested probe: ${res.probe}` : null].filter(Boolean).join("\n"));
    }catch(e:any){ setHint(e.message); } finally{ setBusy(false); }
  }
  return (
    <div className="grid gap-2">
      <div className="flex gap-2">
        <button disabled={!can||busy} className="button" onClick={()=>ask("position")}>Hint: position</button>
        <button disabled={!can||busy} className="button" onClick={()=>ask("operator")}>Hint: operator</button>
        <button disabled={!can||busy} className="button" onClick={coach}>Coach me</button>
      </div>
      <pre className="whitespace-pre-wrap text-sm text-neutral-300 bg-neutral-900 rounded-xl p-3 min-h-[3rem]">{hint ?? "Hints and coaching tips appear here."}</pre>
    </div>
  );
}
