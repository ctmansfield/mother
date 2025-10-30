import React, { createContext, useContext, useMemo, useReducer } from "react";
import type { TileState } from "../types";

type ActiveGame = {
  gameId: string;
  userId: string;
  length: number;
  maxAttempts: number;
  attemptsUsed: number;
  status: "active" | "won" | "lost";
};

type KeyboardState = Record<string, TileState | undefined>;
type Heatmap = Record<string, number>;

type State = {
  game?: ActiveGame;
  guesses: { guess: string; tiles: TileState[] }[];
  keyboard: KeyboardState;
  heatmap: Heatmap;
  constraints?: unknown; // raw coach constraints for viz page
};

type Action =
  | { type: "NEW_GAME"; game: ActiveGame }
  | { type: "ADD_RESULT"; guess: string; tiles: TileState[]; attemptsUsed: number; status?: ActiveGame["status"] }
  | { type: "UPDATE_CONSTRAINTS"; constraints: unknown }
  | { type: "RESET" };

const GAME_KEY = "nerdle.game.v1";

const initial: State = (() => {
  const raw = localStorage.getItem(GAME_KEY);
  if (raw) return JSON.parse(raw);
  return { guesses: [], keyboard: {}, heatmap: {} } as State;
})();

function persist(next: State) {
  localStorage.setItem(GAME_KEY, JSON.stringify(next));
  return next;
}

function mergeKeyState(prev: TileState | undefined, next: TileState): TileState {
  const rank = { empty: 0, absent: 1, present: 2, correct: 3 } as const;
  if (!prev) return next;
  return rank[next] > rank[prev] ? next : prev;
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "NEW_GAME": {
      const next: State = {
        game: action.game,
        guesses: [],
        keyboard: {},
        heatmap: {},
      };
      return persist(next);
    }
    case "ADD_RESULT": {
      const { guess, tiles, attemptsUsed, status } = action;
      const entries = guess.split("");
      const keyboard = { ...state.keyboard };
      const heatmap = { ...state.heatmap };

      entries.forEach((ch, i) => {
        const t = tiles[i] ?? "empty";
        keyboard[ch] = mergeKeyState(keyboard[ch], t);
        heatmap[ch] = (heatmap[ch] ?? 0) + 1;
      });

      const next: State = {
        ...state,
        guesses: [...state.guesses, { guess, tiles }],
        keyboard,
        heatmap,
        game: state.game
          ? { ...state.game, attemptsUsed, status: status ?? state.game.status }
          : state.game,
      };
      return persist(next);
    }
    case "UPDATE_CONSTRAINTS": {
      const next = { ...state, constraints: action.constraints };
      return persist(next);
    }
    case "RESET":
      return persist({ guesses: [], keyboard: {}, heatmap: {} });
    default:
      return state;
  }
}

const Ctx = createContext<{ state: State; dispatch: React.Dispatch<Action> }>({
  state: initial,
  dispatch: () => {},
});

export function GameProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial);
  const value = useMemo(() => ({ state, dispatch }), [state]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useGame() {
  return useContext(Ctx);
}
