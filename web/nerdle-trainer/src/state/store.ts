export const state = { userId: 'u_local', maxAttempts: 6, length: 8, ops: '+-*/=', difficulty: 'normal', gameId: null, attemptsUsed: 0, history: [] }


;



import { create } from "zustand";
import { api, StartResp, GuessResp } from "../services/api";
type Settings = {
  apiBase: string;        // e.g. "/nerdle" (proxied) or "http://10.10.10.2:8082"
  defaultLength: number;  // 8 or 6/7/9…
  ops: string;            // "+-*/="
};

type Game = {
  gameId: string | null;
  userId: string;
  length: number;
  status: "idle" | "active" | "won" | "lost";
  attemptsUsed: number;
  history: { guess: string; tiles?: GuessResp["tiles"] }[];
  constraints?: CoachResp["constraints"];
};

type Store = {
  settings: Settings;
  game: Game;
  setSettings: (s: Partial<Settings>) => void;
  resetGame: () => void;
  startGame: () => Promise<void>;

submitGuess: (guess: string) => Promise<GuessResp>;
  refreshConstraints: () => Promise<void>;
};

// bootstrap from localStorage (safe defaults)
const LS_KEY = "nerdleSettings";
const saved = (() => {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { return {}; }
})();

export const useStore = create<Store>((set, get) => ({
  settings: {
    apiBase: saved.apiBase ?? "/nerdle",
    defaultLength: saved.defaultLength ?? 8,
    ops: saved.ops ?? "+-*/=",
  },
  game: {
    gameId: null,
    userId: "u_chad",
    length: 8,
    status: "idle",
    attemptsUsed: 0,
    history: [],
  },
  setSettings: (s) =>
    set((st) => {
      const next = { ...st.settings, ...s }


;
      localStorage.setItem(LS_KEY, JSON.stringify(next));
      return { settings: next };
    }),

  resetGame: () =>
    set((st) => ({
      game: {
        ...st.game,
        gameId: null,
        status: "idle",
        attemptsUsed: 0,
        history: [],
        constraints: undefined,
        length: st.settings.defaultLength,
      },
    })),

  startGame: async () => {
    const { settings, game } = get();
const client = api;
    const resp: StartResp = await client.start({
      user_id: game.userId,
      difficulty: "normal",
      length: settings.defaultLength,
      ops: settings.ops,
    });
    set({
      game: {
        ...get().game,
        gameId: resp.game_id,
        status: "active",
        attemptsUsed: resp.attempts_used,
        length: resp.length,
        history: [],
      },
    });
  },

  submitGuess: async (guess: string): Promise<GuessResp> => {
      const g = (guess ?? "").trim();
      if (!g) return Promise.resolve({} as GuessResp);

      const s: any = get();

      // 1) Start a game if we don't have one
      if (!s.gameId) {
        const started: StartResp = await api.start({
          user_id: s.userId || "u_local",
          difficulty: s.difficulty ?? s.settings?.difficulty ?? "normal",
          length: s.length ?? s.settings?.length ?? 8,
          ops: s.ops ?? s.settings?.ops ?? "+-*/=",
          max_attempts: s.maxAttempts ?? s.settings?.maxAttempts ?? 6,
        });

        set({
          userId: started.user_id,
          gameId: started.game_id,
          attemptsUsed: (started as any).attempts_used ?? 0,
          status: (started as any).status ?? "active",
          length: (started as any).length ?? (s.length ?? 8),
          maxAttempts: (started as any).max_attempts ?? (s.maxAttempts ?? 6),
        });
      }

      // 2) Now it is safe to guess
      const gid = (get() as any).gameId as string;
      const res: any = await api.guess({
        game_id: gid,
        user_id: (get() as any).userId || "u_local",
        guess: g,
      });

      // 3) Update local state
      set((st: any) => ({
        attemptsUsed: res.attempts_used ?? st.attemptsUsed,
        status: res.status ?? st.status,
        history: Array.isArray(res.tiles)
          ? [...(st.history || []), { guess: g, tiles: res.tiles }]
          : st.history,
        lastHint: res.hint ?? st.lastHint,
      }));

      return res as GuessResp;
    },

  refreshConstraints: async () => {
    const { settings, game } = get();
    if (!game.gameId) return;
const client = api;
    const resp = await client.coach({ game_id: game.gameId, user_id: game.userId }).catch(() => null);
    if (resp?.constraints) set((st) => ({ game: { ...st.game, constraints: resp.constraints } }));
  },
}));

// Create a new game on-demand using current settings.
