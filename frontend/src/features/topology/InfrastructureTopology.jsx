import { Button } from "@arco-design/web-react";
import { IconBranch, IconExpand } from "@arco-design/web-react/icon";
import clsx from "clsx";

const zoneOrder = [
  { key: "east", label: "华东" },
  { key: "south", label: "华南" },
  { key: "north", label: "华北" },
  { key: "central", label: "华中" },
];

function zoneForNode(node) {
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

function ZoneCard({ zone, nodes }) {
  const visibleNodes = nodes.slice(0, zone.key === "east" ? 5 : 4);
  return (
    <div className={clsx("tj-infra-zone", `zone-${zone.key}`)}>
      <div className="tj-infra-zone-title">{zone.label}</div>
      <div className="tj-infra-zone-list">
        {visibleNodes.map((node) => (
          <div className="tj-infra-node-pill" key={node.node_id}>
            <span className={clsx("tj-infra-node-dot", node.online ? "online" : "offline")} />
            <span>{node.node_id}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function InfrastructureTopology({ nodes = [] }) {
  const zones = groupedNodes(nodes);

  return (
    <div className="tj-infra-topology">
      <Button className="tj-infra-expand" type="outline" icon={<IconExpand />} />
      <div className="tj-infra-link horizontal" />
      <div className="tj-infra-link vertical" />
      <div className="tj-infra-hub">
        <IconBranch />
      </div>
      {zoneOrder.map((zone) => (
        <ZoneCard key={zone.key} zone={zone} nodes={zones[zone.key] ?? []} />
      ))}
      <div className="tj-infra-legend">
        <span><i className="online" />在线</span>
        <span><i className="busy" />部分负载</span>
        <span><i className="offline" />离线</span>
      </div>
    </div>
  );
}
