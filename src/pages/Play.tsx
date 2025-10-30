import { useEffect, useMemo, useState } from "react";
import Grid from "../components/Grid";
import Keyboard from "../components/Keyboard";
import { useGame } from "../state/GameContext";
import { api } from "../services/api";
import { normalizeTiles } from "../utils/tiles";
import HintCoachPanel from "../components/HintCoachPanel";
import ConstraintsViz from "../components/ConstraintsViz";

export default function Play() {
  const { state, dispatch } = useGame();
  const game = state.game!;
  const [current, setCurrent] = useState("");

  const done = game.status !== "active";
  const canType = !done && current.length < game.length;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Enter") {
        submit();
        return;
      }
      if (e.key === "Backspace") {
        setCurrent((x) => x.slice(0, -1));
        return;
      }
      const k = e.key;
      if (/^[0-9+\-*/=]$/.test(k)) {
        setCurrent((x) =>
          x.length < game.length ? (x + k).slice(0, game.length) : x
        );
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game.length, done]);

  function onKey(k: string) {
    if (k === "ENTER") return submit();
    if (k === "BACKSPACE") return setCurrent((x) => x.slice(0, -1));
    if (!/^[0-9+\-*/=]$/.test(k)) return;
    if (canType) setCurrent((x) => (x + k).slice(0, game.length));
  }

  async function submit() {
    if (current.length !== game.length || done) return;
    try {
      const res = await api.guess({
        game_id: game.gameId,
        user_id: game.userId,
        guess: current,
      });
      const tiles = normalizeTiles(current, res.tiles);
      dispatch({
        type: "ADD_RESULT",
        guess: current,
        tiles,
        attemptsUsed: res.attempts_used ?? game.attemptsUsed + 1,
        status: res.status,
      });
      setCurrent("");
    } catch (e: any) {
      alert(e.message);
    }
  }

  const composedRows = useMemo(() => {
    const rows = [...state.guesses];
    if (!done && current) {
      rows.push({ guess: current, tiles: Array(game.length).fill("empty") });
    }
    return rows;
  }, [state.guesses, current, game.length, done]);

  return (
    <div className="grid lg:grid-cols-[1fr,320px] gap-6">
      <div className="grid gap-4">
        <div className="bg-neutral-900 rounded-2xl p-4 shadow-soft grid gap-4">
          <div className="flex items-center justify-between text-sm">
            <div>
              Attempts:{" "}
              <span className="font-mono">
                {game.attemptsUsed}/{game.maxAttempts}
              </span>
            </div>
            <div>Status: <span className="font-semibold">{game.status}</span></div>
          </div>
          <Grid length={game.length} rows={composedRows} />
          <Keyboard onKey={onKey} keyStates={state.keyboard} heatmap={state.heatmap} />
        </div>

        <div className="bg-neutral-900 rounded-2xl p-4 shadow-soft grid gap-3">
          <HintCoachPanel />
        </div>
      </div>

      <aside className="grid gap-4">
        <div className="bg-neutral-900 rounded-2xl p-4 shadow-soft">
          <div className="text-sm font-semibold mb-2">Constraints</div>
          <ConstraintsViz cns={state.constraints as any} />
        </div>
      </aside>
    </div>
  );
}
