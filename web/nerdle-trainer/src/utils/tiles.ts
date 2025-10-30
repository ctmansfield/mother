import type { ServerTile, TileState } from "../types";
export function normalizeTiles(guess: string, tiles?: ServerTile[] | null): TileState[] {
  const g = guess.split("");
  if (!tiles || tiles.length === 0) return g.map(() => "empty");
  if (typeof tiles[0] === "string") return (tiles as string[]).map(toTileState);
  return (tiles as { ch?: string; state: string }[]).map((t) => toTileState(t.state) ?? "empty");
}
function toTileState(s: string): TileState { return s==="correct"||s==="present"||s==="absent" ? s : "empty"; }
