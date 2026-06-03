import { Button, Card, Descriptions, Drawer, Grid, Table } from "@arco-design/web-react";
import { IconCheckCircle, IconCommand, IconSafe, IconStorage } from "@arco-design/web-react/icon";
import { useMemo, useState } from "react";
import { EmptyState } from "../features/common/EmptyState.jsx";
import { PageHeader } from "../features/common/PageHeader.jsx";
import { InfrastructureTopology } from "../features/topology/InfrastructureTopology.jsx";
import { useControlPlaneContext } from "../layout/ControlPlaneProvider.jsx";
import { num, pct, regionLabel } from "../utils/format.js";

const { Row, Col } = Grid;

function InfraMetric({ icon, title, value, tone = "blue" }) {
  return (
    <Card className={`tj-infra-metric tone-${tone}`} bordered={false}>
      <span className="tj-infra-metric-icon">{icon}</span>
      <div>
        <span>{title}</span>
        <b>{value}</b>
      </div>
    </Card>
  );
}

function onlineCell(online) {
  return (
    <span className={online ? "tj-infra-online online" : "tj-infra-online offline"}>
      <i />
      {online ? "online" : "offline"}
    </span>
  );
}

export function InfrastructurePage() {
  const { report, state } = useControlPlaneContext();
  const [activeNode, setActiveNode] = useState(null);
  const regions = useMemo(() => new Set(state.nodes.map((node) => node.service_region ?? node.location ?? node.region)).size, [state.nodes]);

  return (
    <div className="tj-page tj-page-infrastructure">
      <PageHeader eyebrow="P4 / INFRASTRUCTURE" title="基础设施" />
      <Row gutter={[20, 20]} className="tj-infra-metric-row">
        <Col span={6}><InfraMetric title="节点总数" value={state.nodeCount} icon={<IconStorage />} /></Col>
        <Col span={6}><InfraMetric title="在线节点" value={state.onlineNodes} icon={<IconCheckCircle />} tone="green" /></Col>
        <Col span={6}><InfraMetric title="服务区域" value={regions} icon={<IconCommand />} tone="purple" /></Col>
        <Col span={6}><InfraMetric title="网络风险" value={num(report?.metrics?.average_network_risk, 3)} icon={<IconSafe />} tone="amber" /></Col>
      </Row>
      <div className="tj-infra-main">
        <Card title="拓扑图" bordered={false} className="tj-panel tj-infra-panel tj-infra-topology-card">
          {state.nodes.length ? <InfrastructureTopology nodes={state.nodes} topology={report?.physical_topology} /> : <EmptyState description="等待节点注册" />}
        </Card>
        <Card title="节点表格" bordered={false} className="tj-panel tj-infra-panel tj-infra-table-card">
          <Table
            className="tj-infra-table"
            rowKey="node_id"
            data={state.nodes}
            pagination={{ pageSize: 8, showTotal: true }}
            columns={[
              { title: "节点", dataIndex: "node_id", width: 118 },
              { title: "服务区", width: 72, render: (_, node) => regionLabel(node.service_region ?? node.location ?? node.region) },
              { title: "接入", width: 84, render: (_, node) => regionLabel(node.region) },
              { title: "在线", width: 92, render: (_, node) => onlineCell(node.online) },
              { title: "健康", width: 78, render: (_, node) => pct(node.health_score) },
              { title: "可靠性", width: 84, render: (_, node) => pct(node.reliability_score) },
              { title: "详情", width: 58, render: (_, node) => <Button className="tj-infra-view" type="text" size="mini" onClick={() => setActiveNode(node)}>查看</Button> },
            ]}
          />
        </Card>
      </div>
      <Drawer width={520} title="节点详情" visible={Boolean(activeNode)} onCancel={() => setActiveNode(null)} footer={null}>
        {activeNode ? (
          <Descriptions
            column={1}
            data={[
              { label: "节点 ID", value: activeNode.node_id },
              { label: "区域", value: regionLabel(activeNode.service_region ?? activeNode.location ?? activeNode.region) },
              { label: "健康度", value: pct(activeNode.health_score) },
              { label: "可靠性", value: pct(activeNode.reliability_score) },
              { label: "CPU 可用", value: `${num(activeNode.available?.cpu, 0)} / ${num(activeNode.capacity?.cpu, 0)}` },
              { label: "内存可用", value: `${num(activeNode.available?.memory, 0)} / ${num(activeNode.capacity?.memory, 0)} GB` },
              { label: "标签", value: (activeNode.labels ?? []).join(", ") || "-" },
            ]}
          />
        ) : null}
      </Drawer>
    </div>
  );
}
