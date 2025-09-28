export type Vars = Record<string, number>;

export interface Choice {
  id: string;
  label: string;
  to: string;
  effects: Vars;
}

export interface Node {
  id: string;
  title: string;
  text: Record<string, string>;
  choices: Choice[];
}

export interface RunState {
  nodeId: string;
  vars: Vars;
  log: string[];
}

export const initState = (startNode: string): RunState => ({
  nodeId: startNode,
  vars: { mut: 0, klarheit: 0 },
  log: []
});
