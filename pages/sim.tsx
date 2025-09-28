"use client";
import React, { useState } from "react";
import story from "../story/example.story.json";
import { initState, RunState, Node } from "../engine/state";
import { step } from "../engine/stepper";
import LensRenderer from "../components/LensRenderer";

const SimPage: React.FC = () => {
  const nodes = (story as any).nodes as Node[];
  const [state, setState] = useState<RunState>(initState("start"));
  const [lens, setLens] = useState<"base" | "narrator" | "observer">("base");

  const node = nodes.find(n => n.id === state.nodeId)!;

  const handleChoice = (choiceId: string) => {
    const choice = node.choices.find(c => c.id === choiceId);
    if (choice) setState(prev => step(prev, nodes, choice));
  };

  return (
    <div className="max-w-xl mx-auto p-6">
      <LensRenderer node={node} lens={lens} />

      <div className="flex gap-2 my-4">
        {node.choices.map(choice => (
          <button
            key={choice.id}
            className="px-3 py-2 bg-blue-500 text-white rounded-lg"
            onClick={() => handleChoice(choice.id)}
          >
            {choice.label}
          </button>
        ))}
      </div>

      <div className="flex gap-2">
        {(["base", "narrator", "observer"] as const).map(l => (
          <button
            key={l}
            className={`px-3 py-1 border rounded-lg ${lens === l ? "bg-gray-200" : ""}`}
            onClick={() => setLens(l as any)}
          >
            {l}
          </button>
        ))}
      </div>

      <div className="mt-4">
        <h3 className="font-semibold">State</h3>
        <pre className="bg-gray-100 p-2 rounded">{JSON.stringify(state, null, 2)}</pre>
      </div>
    </div>
  );
};

export default SimPage;
