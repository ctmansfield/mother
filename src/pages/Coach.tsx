import ConstraintsViz from "../components/ConstraintsViz";
import HintCoachPanel from "../components/HintCoachPanel";
import { useGame } from "../state/GameContext";

export default function CoachPage() {
  const { state } = useGame();
  return (
    <div className="grid md:grid-cols-2 gap-6">
      <div className="bg-neutral-900 rounded-2xl p-4 shadow-soft grid gap-3">
        <div className="text-sm font-semibold">Ask the coach</div>
        <HintCoachPanel />
      </div>
      <div className="bg-neutral-900 rounded-2xl p-4 shadow-soft">
        <div className="text-sm font-semibold mb-2">Constraint visualizer</div>
        <ConstraintsViz cns={state.constraints as any} />
      </div>
    </div>
  );
}
