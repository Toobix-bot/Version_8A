import React from "react";
import { Node } from "../engine/state";

interface Props {
  node: Node;
  lens: "base" | "narrator" | "observer";
}

const LensRenderer: React.FC<Props> = ({ node, lens }) => {
  return (
    <div className="p-4 rounded-xl shadow-md bg-white dark:bg-gray-800">
      <h2 className="text-xl font-bold mb-2">{node.title}</h2>
      <p className="mb-4">{node.text[lens] || node.text.base}</p>
    </div>
  );
};

export default LensRenderer;
