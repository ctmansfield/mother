import { useState } from "react";
import { useSettingsStore } from "../state/settings.store";

export function SettingsPage() {
  const st = useSettingsStore();
  const [apiBase, setApiBase] = useState(st.apiBase);
  const [length, setLength] = useState(st.length);
  const [ops, setOps] = useState(st.ops);

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Settings</h2>

      <div className="grid gap-4 max-w-xl">
        <Field label="API Base">
          <input className="input" value={apiBase}
                 onChange={e=>setApiBase(e.target.value)}
                 placeholder="/nerdle or http://10.10.10.2:8082/nerdle"/>
        </Field>

        <Field label="Length">
          <input className="input" type="number" min={5} max={12}
                 value={length} onChange={e=>setLength(parseInt(e.target.value||"8"))}/>
        </Field>

        <Field label="Allowed Ops">
          <input className="input" value={ops} onChange={e=>setOps(e.target.value)} />
        </Field>

        <div className="flex gap-2">
          <button className="btn" onClick={()=>st.reset()}>Reset</button>
          <button className="btn-primary" onClick={()=>st.setAll({apiBase, length, ops})}>
            Save
          </button>
        </div>
      </div>

      <style>{styles}</style>
    </div>
  );
}

function Field({label, children}:{label:string; children:React.ReactNode}) {
  return (
    <label className="grid gap-1">
      <span className="text-sm text-zinc-400">{label}</span>
      {children}
    </label>
  );
}

const styles = `
.input{ @apply px-3 py-2 rounded-md bg-zinc-900 border border-zinc-800 outline-none focus:border-zinc-600; }
.btn{ @apply px-3 py-2 rounded-md bg-zinc-800 hover:bg-zinc-700; }
.btn-primary{ @apply px-3 py-2 rounded-md bg-indigo-600 hover:bg-indigo-500; }
`;
