import { TileState } from "../types";
import clsx from "clsx";

export default function Grid({
  length,
  rows,
}: {
  length: number;
  rows: { guess: string; tiles: TileState[] }[];
}) {
  const maxRows = Math.max(rows.length + 1, 6);
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: maxRows }).map((_, r) => {
        const data = rows[r];
        const letters = data?.guess ?? "";
        const tiles = data?.tiles ?? [];
        return (
          <div key={r} className="flex gap-2">
            {Array.from({ length }).map((__, c) => {
              const ch = letters[c] ?? "";
              const state = tiles[c] ?? (ch ? "empty" : "empty");
              return (
                <div
                  key={c}
                  className={clsx("tile", {
                    "tile-correct": state === "correct",
                    "tile-present": state === "present",
                    "tile-absent": state === "absent",
                  })}
                >
                  {ch}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
