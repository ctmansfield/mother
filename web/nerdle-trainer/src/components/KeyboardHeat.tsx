import React, { useMemo } from "react";
import clsx from "clsx";

const KEYS = ["1","2","3","4","5","6","7","8","9","0","+","-","*","/","="];

export function KeyboardHeat({ guesses }: { guesses: string[] }) {
  const counts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const g of guesses) for (const ch of g) m[ch] = (m[ch] ?? 0) + 1;
    return m;
  }, [guesses]);

  const max = useMemo(() => Math.max(1, ...Object.values(counts)), [counts]);

  return (
    <div>
      <div className="text-sm text-zinc-400 mb-2">Keyboard heat</div>
      <div className="grid grid-cols-10 gap-2 max-w-xl">
        {KEYS.map((k) => {
          const n = counts[k] ?? 0;
          const alpha = n === 0 ? 0.08 : 0.15 + 0.75 * (n / max);
          return (
            <div
              key={k}
              className={clsx(
                "h-10 rounded-md flex items-center justify-center border border-zinc-800 text-sm",
                n === 0 ? "text-zinc-500" : "text-white"
              )}
              style={{ backgroundColor: `rgba(16, 185, 129, ${alpha})` }} // emerald with alpha
              title={`${k}: ${n}`}
            >
              {k}
            </div>
          );
        })}
      </div>
    </div>
  );
}
