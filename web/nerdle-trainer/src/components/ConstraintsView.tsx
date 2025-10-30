import React from "react";

type Constraints = {
  must_have?: string[];
  cannot_have?: string[];
  fixed?: Record<number, string>;
};

export function ConstraintsView({ cns, length }: { cns?: Constraints; length: number }) {
  const fixed = cns?.fixed ?? {};
  const must = cns?.must_have ?? [];
  const cant = cns?.cannot_have ?? [];

  return (
    <div className="grid sm:grid-cols-2 gap-8">
      <div>
        <div className="text-sm text-zinc-400 mb-2">Constraints</div>
        <div className="text-sm grid grid-cols-3 gap-y-1">
          <div className="text-zinc-400">Must have</div>
          <div className="col-span-2">{must.length ? must.join(" ") : <span className="text-zinc-500">(none)</span>}</div>

          <div className="text-zinc-400">Cannot have</div>
          <div className="col-span-2">{cant.length ? cant.join(" ") : <span className="text-zinc-500">(none)</span>}</div>

          <div className="text-zinc-400">Fixed positions</div>
          <div className="col-span-2">{Object.keys(fixed).length ? "" : <span className="text-zinc-500">(none)</span>}</div>
        </div>

        <div className="mt-3 grid grid-cols-8 gap-2">
          {Array.from({ length }, (_, i) => (
            <div key={i} className="h-10 rounded-md border border-zinc-800 flex items-center justify-center text-lg font-semibold"
                 style={fixed[i] ? { backgroundColor: "rgba(16,185,129,0.35)" } : undefined}>
              {fixed[i] ?? ""}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
