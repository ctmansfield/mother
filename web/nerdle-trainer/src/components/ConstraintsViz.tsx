import { Constraints } from "../types";
import clsx from "clsx";
const ALL="0123456789+-*/=";
export default function ConstraintsViz({ cns }: { cns?: Constraints }){
  if(!cns) return <div className="text-sm text-neutral-400">Coaching constraints will appear here after you press “Coach me”.</div>;
  const must=new Set(cns.must_have ?? []), cannot=new Set(cns.cannot_have ?? []), fixed=cns.fixed ?? {}, banned=cns.banned ?? {};
  return (
    <div className="grid gap-3">
      <div>
        <div className="text-xs uppercase text-neutral-400 mb-2">Alphabet</div>
        <div className="flex flex-wrap gap-1">
          {ALL.split("").map(ch=>{
            const tone = must.has(ch) ? "bg-key.correct" : cannot.has(ch) ? "bg-key.absent" : "bg-neutral-700";
            return <span key={ch} className={clsx("px-2 py-1 rounded-md text-sm font-mono", tone)} title={describeChar(ch,fixed,banned)}>{ch}</span>;
          })}
        </div>
      </div>
      {Object.keys(fixed).length>0 && (
        <div>
          <div className="text-xs uppercase text-neutral-400 mb-2">Fixed positions</div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(fixed).map(([pos,ch])=>(
              <span key={pos} className="px-2 py-1 rounded-md text-sm font-mono bg-key.correct">{Number(pos)+1}: {ch}</span>
            ))}
          </div>
        </div>
      )}
      {Object.keys(banned).length>0 && (
        <div>
          <div className="text-xs uppercase text-neutral-400 mb-2">Banned positions</div>
          <div className="flex flex-col gap-1">
            {Object.entries(banned).map(([pos,arr])=>(
              <div key={pos} className="text-sm"><span className="font-mono text-neutral-300 mr-1">{Number(pos)+1}:</span><span className="font-mono">{arr?.join(" ")}</span></div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
function describeChar(ch:string, fixed:Record<number,string>, banned:Record<number,string[]>){
  const locks=Object.entries(fixed).filter(([,c])=>c===ch).map(([i])=>Number(i)+1);
  const bans=Object.entries(banned).filter(([,arr])=>arr?.includes(ch)).map(([i])=>Number(i)+1);
  const bits=[] as string[]; if(locks.length) bits.push(`fixed @ ${locks.join(", ")}`); if(bans.length) bits.push(`banned @ ${bans.join(", ")}`); return bits.join("; ") || ch;
}
