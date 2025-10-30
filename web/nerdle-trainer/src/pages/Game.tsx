import React, { useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "../state/store";
import { KeyboardHeat } from "../components/KeyboardHeat";
import { ConstraintsView } from "../components/ConstraintsView";

export default function GamePage() {
  const { game, settings, submitGuess, refreshConstraints } = useStore();
  const [guess, setGuess] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const guesses = useMemo(() => game.history.map((h) => h.guess), [game.history]);

  async function onSubmit() {
    if (!guess.trim()) return;
    await submitGuess(guess.trim());
    setGuess("");
    inputRef.current?.focus();
    refreshConstraints().catch(() => {});
  }

  useEffect(() => {
    if (game.status === "active" && !game.constraints) {
      refreshConstraints().catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game.gameId]);

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      <div className="text-sm text-zinc-400">
        <span className="font-medium text-zinc-200">New Game</span>
        <span className="ml-3">Length: {game.length}</span>
        <span className="ml-3">• Ops: {settings.ops}</span>
      </div>

      <div>
        <label className="block text-sm text-zinc-300 mb-2">Guess</label>
        <input
          ref={inputRef}
          value={guess}
          onChange={(e) => setGuess(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSubmit()}
          className="w-full max-w-xl bg-zinc-800 text-zinc-100 rounded px-3 py-2 outline-none focus:ring-2 ring-emerald-500"
          placeholder={`${game.length} chars expression, e.g. 9+3-10=2`}
        />
        <div className="text-xs text-zinc-500 mt-2">
          Press Enter to submit. Status: <span className="text-zinc-300">{game.status}</span> • Attempts: {game.attemptsUsed}
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-10">
        <KeyboardHeat guesses={guesses} />
        <ConstraintsView cns={game.constraints} length={game.length} />
      </div>
    </div>
  );
}
