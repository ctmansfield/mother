import type {
  StartRequest,
  StartResponse,
  GuessRequest,
  GuessResponse,
  HintRequest,
  HintResponse,
  CoachResponse,
} from "../types";
import { getSettings } from "../state/SettingsContext";

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`HTTP ${res.status}: ${txt}`);
  }
  return (await res.json()) as T;
}

export const api = {
  async start(req: StartRequest) {
    const base = getSettings().apiBase;
    return j<StartResponse>(
      await fetch(`${base}/nerdle/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(req),
      })
    );
  },

  async guess(req: GuessRequest) {
    const base = getSettings().apiBase;
    return j<GuessResponse>(
      await fetch(`${base}/nerdle/guess`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(req),
      })
    );
  },

  async hint(req: HintRequest) {
    const base = getSettings().apiBase;
    return j<HintResponse>(
      await fetch(`${base}/nerdle/hint`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(req),
      })
    );
  },

  async coach(game_id: string, user_id: string) {
    const base = getSettings().apiBase;
    return j<CoachResponse>(
      await fetch(`${base}/nerdle/coach`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ game_id, user_id }),
      })
    );
  },
};
