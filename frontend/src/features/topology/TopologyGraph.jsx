import { Graph } from "@antv/g6";
import { useEffect, useRef } from "react";

export function TopologyGraph({ nodes = [], topology }) {
  const hostRef = useRef(null);

  useEffect(() => {
    if (!hostRef.current) return undefined;
    const topologyNodeIds = new Set((topology?.topology_nodes ?? []).map(String));
    const computeNodes = nodes.slice(0, 48);
    const computeNodeIds = new Set(computeNodes.map((node) => String(node.node_id)));
    const physicalEdges = topology?.topology_edges ?? [];
    const attachments = topology?.compute_attachments ?? {};
    const attachmentAnchors = Object.values(attachments).map(String);
    for (const edge of physicalEdges) {
      if (edge?.source) topologyNodeIds.add(String(edge.source));
      if (edge?.target) topologyNodeIds.add(String(edge.target));
    }
    for (const anchor of attachmentAnchors) {
      topologyNodeIds.add(anchor);
    }

    const physicalNodes = [...topologyNodeIds].map((id) => ({
      id,
      type: "topology",
      style: {
        labelText: id.slice(0, 18),
        fill: "#f7f2df",
        stroke: "#b7791f",
        size: 42,
      },
    }));
    const graphComputeNodes = computeNodes.map((node) => ({
      id: node.node_id,
      type: "compute",
      data: node,
      style: {
        labelText: node.node_id.replace("dci-", "").slice(0, 18),
        fill: node.online ? "#e9fbf7" : "#fff1f0",
        stroke: node.online ? "#2a9d8f" : "#f53f3f",
        size: 32,
      },
    }));
    const graphNodes = [...physicalNodes, ...graphComputeNodes];
    const graphNodeIds = new Set(graphNodes.map((node) => String(node.id)));
    const graphEdges = [
      ...physicalEdges.map((edge, index) => ({
        id: `physical-${index}`,
        source: String(edge.source ?? ""),
        target: String(edge.target ?? ""),
        style: { stroke: "#9aa8b2", lineWidth: 1.6 },
      })),
      ...Object.entries(attachments)
        .filter(([computeId]) => computeNodeIds.has(String(computeId)))
        .map(([computeId, anchor]) => ({
          id: `attach-${computeId}`,
          source: String(computeId),
          target: String(anchor),
          style: { stroke: "#2a9d8f", lineDash: [6, 5], lineWidth: 1.2 },
        })),
    ];
    const safeEdges = graphEdges.filter((edge) => graphNodeIds.has(edge.source) && graphNodeIds.has(edge.target));
    const fallbackEdges = graphNodes.slice(1).map((node, index) => ({
      id: `fallback-${index}`,
      source: graphNodes[0]?.id,
      target: node.id,
    }));
    const graph = new Graph({
      container: hostRef.current,
      width: hostRef.current.clientWidth,
      height: 420,
      data: { nodes: graphNodes, edges: safeEdges.length ? safeEdges : fallbackEdges.filter((edge) => edge.source && edge.target) },
      layout: { type: "force" },
      node: {
        style: {
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
