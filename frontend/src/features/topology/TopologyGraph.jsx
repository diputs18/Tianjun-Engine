import { Graph } from "@antv/g6";
import { useEffect, useRef } from "react";

export function TopologyGraph({ nodes = [], topology }) {
  const hostRef = useRef(null);

  useEffect(() => {
    if (!hostRef.current) return undefined;
    const graphNodes = nodes.slice(0, 24).map((node) => ({
      id: node.node_id,
      data: node,
      style: {
        labelText: node.node_id.replace("dci-", "").slice(0, 18),
        fill: node.online ? "#e9fbf7" : "#fff1f0",
        stroke: node.online ? "#2a9d8f" : "#f53f3f",
      },
    }));
    const physicalEdges = topology?.edges ?? [];
    const graphEdges = physicalEdges.length
      ? physicalEdges.map((edge, index) => ({ id: `edge-${index}`, source: edge.source, target: edge.target }))
      : graphNodes.slice(1).map((node, index) => ({
          id: `edge-${index}`,
          source: graphNodes[0]?.id,
          target: node.id,
        }));
    const graph = new Graph({
      container: hostRef.current,
      width: hostRef.current.clientWidth,
      height: 420,
      data: { nodes: graphNodes, edges: graphEdges.filter((edge) => edge.source && edge.target) },
      layout: { type: "force" },
      node: {
        style: {
          size: 34,
          labelFontSize: 10,
          labelPlacement: "bottom",
        },
      },
      edge: {
        style: { stroke: "#b8c4cc", lineWidth: 1.2 },
      },
      behaviors: ["drag-canvas", "zoom-canvas", "drag-element"],
    });
    graph.render();
    return () => graph.destroy();
  }, [nodes, topology]);

  return <div ref={hostRef} className="tj-topology-graph" />;
}
