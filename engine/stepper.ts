import { RunState, Node, Choice } from "./state";

export const applyEffects = (state: RunState, effects: Record<string, number>): RunState => {
  const newVars = { ...state.vars };
  for (const key in effects) {
    newVars[key] = (newVars[key] || 0) + effects[key];
  }
  return { ...state, vars: newVars };
};

export const step = (state: RunState, nodes: Node[], choice: Choice): RunState => {
  const target = nodes.find(n => n.id === choice.to);
  if (!target) return state;

  const updated = applyEffects(state, choice.effects);
  return {
    ...updated,
    nodeId: target.id,
    log: [...state.log, `Choice: ${choice.label}`]
  };
};
