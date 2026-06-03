import { Button } from "@arco-design/web-react";
import { IconBranch, IconLeft } from "@arco-design/web-react/icon";
import clsx from "clsx";

export const zoneOrder = [
  { key: "east", label: "华东" },
  { key: "south", label: "华南" },
  { key: "north", label: "华北" },
  { key: "central", label: "华中" },
];

const nodeSlots = [
  { x: 50, y: 18 },
  { x: 78, y: 30 },
  { x: 84, y: 58 },
  { x: 66, y: 78 },
  { x: 34, y: 78 },
  { x: 16, y: 58 },
  { x: 22, y: 30 },
  { x: 50, y: 86 },
];

export function zoneForNode(node) {
  const raw = `${node.service_region ?? ""} ${node.location ?? ""} ${node.region ?? ""} ${node.node_id ?? ""}`.toLowerCase();
  if (raw.includes("south") || raw.includes("shenzhen") || raw.includes("guangzhou") || raw.includes("sz-") || raw.includes("gz-")) return "south";
  if (raw.includes("north") || raw.includes("beijing") || raw.includes("bj-")) return "north";
  if (raw.includes("central") || raw.includes("wuhan") || raw.includes("wh-")) return "central";
  return "east";
}

function groupedNodes(nodes) {
  const groups = Object.fromEntries(zoneOrder.map((zone) => [zone.key, []]));
  for (const node of nodes) {
    groups[zoneForNode(node)]?.push(node);
  }
  return groups;
}

function ZoneCard({ zone, nodes, onSelect }) {
  const onlineCount = nodes.filter((node) => node.online).length;

  return (
    <button type="button" className={clsx("tj-infra-zone", `zone-${zone.key}`)} onClick={() => onSelect(zone.key)}>
      <span className="tj-infra-zone-title">
        {zone.label}
        <span className="tj-infra-zone-count">{nodes.length}</span>
      </span>
      <span className="tj-infra-zone-summary">
        <span><i className="online" />{onlineCount} 在线</span>
        <span>{nodes.length - onlineCount} 离线</span>
      </span>
      <span className="tj-infra-zone-enter">进入区域</span>
    </button>
  );
}

function NodePill({ node, active, slot, onSelect }) {
  return (
    <button
      type="button"
      className={clsx("tj-infra-node-pill tj-infra-node-action", active && "selected")}
      style={{ "--node-x": `${slot.x}%`, "--node-y": `${slot.y}%` }}
      onClick={() => onSelect(node)}
    >
      <span className={clsx("tj-infra-node-dot", node.online ? "online" : "offline")} />
      <span>{node.node_id}</span>
    </button>
  );
}

function RegionDetail({ zone, nodes, activeNodeId, onBack, onNodeSelect }) {
  const zoneInfo = zoneOrder.find((item) => item.key === zone);
  const accessName = zone === "east" ? "shanghai" : zone === "south" ? "深圳" : zone === "north" ? "beijing" : "wuhan";
  const visibleNodes = nodes.slice(0, nodeSlots.length);
  const hiddenCount = Math.max(nodes.length - visibleNodes.length, 0);

  return (
    <div className="tj-infra-zone-detail">
      <div className="tj-infra-drillbar">
        <Button type="text" size="small" icon={<IconLeft />} onClick={onBack}>返回区域总览</Button>
        <span>{zoneInfo?.label ?? "区域"} · {nodes.length} 个节点</span>
      </div>
      <div className="tj-infra-detail-ring" />
      <div className="tj-infra-detail-hub">
        <IconBranch />
        <span>{accessName}</span>
      </div>
      {visibleNodes.map((node, index) => (
        <NodePill
          key={node.node_id}
          node={node}
          active={node.node_id === activeNodeId}
          slot={nodeSlots[index]}
          onSelect={onNodeSelect}
        />
      ))}
      {hiddenCount > 0 ? <div className="tj-infra-detail-more">+ {hiddenCount} 个节点在表格中查看</div> : null}
    </div>
  );
}

export function InfrastructureTopology({
  nodes = [],
  selectedZone,
  activeNodeId,
  onZoneSelect,
  onZoneReset,
  onNodeSelect,
}) {
  const zones = groupedNodes(nodes);
  const selectedNodes = selectedZone ? zones[selectedZone] ?? [] : [];

  return (
    <div className={clsx("tj-infra-topology", selectedZone && "is-drilldown")}>
      {selectedZone ? (
        <RegionDetail
          zone={selectedZone}
          nodes={selectedNodes}
          activeNodeId={activeNodeId}
          onBack={onZoneReset}
          onNodeSelect={onNodeSelect}
        />
      ) : (
        <>
          <div className="tj-infra-link horizontal" />
          <div className="tj-infra-link vertical" />
          <div className="tj-infra-hub">
            <IconBranch />
          </div>
          {zoneOrder.map((zone) => (
            <ZoneCard key={zone.key} zone={zone} nodes={zones[zone.key] ?? []} onSelect={onZoneSelect} />
          ))}
          <div className="tj-infra-legend">
            <span><i className="online" />在线</span>
            <span><i className="offline" />离线</span>
          </div>
        </>
      )}
    </div>
  );
}
