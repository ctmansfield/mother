import clsx from "clsx";
import { TileState } from "../types";

const rows = [
  ["7", "8", "9", "+", "-"],
  ["4", "5", "6", "*", "/"],
  ["1", "2", "3", "=", "0"],
];

export default function Keyboard({
  onKey,
  keyStates,
  heatmap,
}: {
  onKey: (k: string) => void;
  keyStates: Record<string, TileState | undefined>;
  heatmap: Record<string, number>;
}) {
  const max = Math.max(1, ...Object.values(heatmap));
  return (
    <div className="flex flex-col gap-2">
      {rows.map((r, i) => (
        <div key={i} className="flex gap-2">
          {r.map((k) => {
            const st = keyStates[k] ?? "empty";
            const hit = heatmap[k] ?? 0;
            return (
              <button
                key={k}
                className={clsx(
                  "button w-12 h-12 rounded-xl font-bold text-lg",
                  {
                    "bg-key.correct": st === "correct",
                    "bg-key.present": st === "present",
                    "bg-key.absent": st === "absent",
                    "bg-neutral-700": st === "empty",
                  }
                )}
                style={{
                  boxShadow:
                    hit > 0
                      ? `inset 0 -${Math.round((hit / max) * 12)}px 0 0 rgba(255,255,255,.15)`
                      : undefined,
                }}
                onClick={() => onKey(k)}
              >
                {k}
              </button>
            );
          })}
        </div>
      ))}
      <div className="flex gap-2">
        <button className="button flex-1" onClick={() => onKey("BACKSPACE")}>
          ←
        </button>
        <button className="button flex-1" onClick={() => onKey("ENTER")}>
          Enter
        </button>
      </div>
    </div>
  );
}
