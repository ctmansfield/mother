export type StartPayload = {
  user_id: string;
  difficulty?: string;
  length?: number;
  ops?: string;
  max_attempts?: number;
};
export type StartResp = {
  game_id: string;
  user_id: string;
  length: number;
  max_attempts: number;
  attempts_used: number;
  status: string;
};

export type GuessPayload = { game_id: string; user_id: string; guess: string };
export type GuessResp = {
  valid: boolean;
  reason?: string | null;
  tiles: any[] | null;
  attempts_used: number;
  attempts_left: number;
  status: string;
  hint?: string | null;
};

export type HintPayload  = { game_id: string; user_id: string; kind: "position" | "operator" | "must_have" };
export type CoachPayload = { game_id: string; user_id: string };
export type CoachResp = { tips?: string[]; [k: string]: any };

let apiBase = (import.meta as any).env?.VITE_API_BASE?.trim() || "/nerdle"; // default: dev proxy path

export function setApiBase(next?: string) {
  apiBase = (next?.trim() || "/nerdle").replace(/\/+$/, "");
}

function join(base: string, path: string) {
  return path.startsWith("/") ? `${base}${path}` : `${base}/${path}`;
}

async function json<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const res = await fetch(input, {
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${text ? " - " + text : ""}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => json<{ ok: boolean; service: string }>("/health"),

  start: (p: StartPayload) =>
    json<StartResp>(join(apiBase, "/start"), { method: "POST", body: JSON.stringify(p) }),

  guess: (p: GuessPayload) =>
    json<GuessResp>(join(apiBase, "/guess"), { method: "POST", body: JSON.stringify(p) }),

  hint: (p: HintPayload) =>
    json(join(apiBase, "/hint"), { method: "POST", body: JSON.stringify(p) }),

  coach: (p: CoachPayload) =>
    json<CoachResp>(join(apiBase, "/coach"), { method: "POST", body: JSON.stringify(p) }),
};
