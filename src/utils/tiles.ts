import type { ServerTile, TileState } from "../types";

export function normalizeTiles(guess: string, tiles?: ServerTile[] | null): TileState[] {
  const g = guess.split("");
  if (!tiles || tiles.length === 0) return g.map(() => "empty");

  // Case A: server returns ["correct","present",...]
  if (typeof tiles[0] === "string") {
    return (tiles as string[]).map(toTileState);
  }

  // Case B: server returns [{ ch?, state }]
  return (tiles as { ch?: string; state: string }[]).map((t, i) => {
    const s = toTileState(t.state);
    // sanity: if ch present and mismatched, we still color by server state
    return s ?? "empty";
  });
}

function toTileState(s: string): TileState {
  if (s === "correct" || s === "present" || s === "absent") return s;
  return "empty";
}
