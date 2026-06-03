import { Button, Card, Descriptions, Drawer, Grid, Table, Tag } from "@arco-design/web-react";
import { useMemo, useState } from "react";
import { EmptyState } from "../features/common/EmptyState.jsx";
import { KpiCard } from "../features/common/KpiCard.jsx";
import { PageHeader } from "../features/common/PageHeader.jsx";
import { TopologyGraph } from "../features/topology/TopologyGraph.jsx";
import { useControlPlaneContext } from "../layout/ControlPlaneProvider.jsx";
import { num, pct, regionLabel } from "../utils/format.js";

const { Row, Col } = Grid;

export function InfrastructurePage() {
  const { report, state } = useControlPlaneContext();
  const [activeNode, setActiveNode] = useState(null);
  const regions = useMemo(() => new Set(state.nodes.map((node) => node.service_region ?? node.location ?? node.region)).size, [state.nodes]);

  return (
    <div className="tj-page">
      <PageHeader eyebrow="P4 / INFRASTRUCTURE" title="基础设施" description="资源池、节点、拓扑和链路详情拆分展示。" />
      <Row gutter={[16, 16]}>
        <Col span={6}><KpiCard title="节点总数" value={state.nodeCount} /></Col>
        <Col span={6}><KpiCard title="在线节点" value={state.onlineNodes} progress={state.nodeCount ? state.onlineNodes / state.nodeCount : 0} tone="green" /></Col>
        <Col span={6}><KpiCard title="服务区域" value={regions} tone="ink" /></Col>
        <Col span={6}><KpiCard title="网络风险" value={num(report?.metrics?.average_network_risk, 3)} tone="amber" /></Col>
      </Row>
      <Card title="拓扑图" bordered={false} className="tj-panel tj-section-row">
        {state.nodes.length ? <TopologyGraph nodes={state.nodes} topology={report?.physical_topology} /> : <EmptyState description="等待节点注册" />}
      </Card>
      <Card title="节点表格" bordered={false} className="tj-panel tj-section-row">
        <Table
          rowKey="node_id"
          data={state.nodes}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: "节点", dataIndex: "node_id" },
            { title: "服务区", render: (_, node) => regionLabel(node.service_region ?? node.location ?? node.region) },
            { title: "接入", render: (_, node) => regionLabel(node.region) },
            { title: "在线", render: (_, node) => <Tag color={node.online ? "green" : "red"}>{node.online ? "online" : "offline"}</Tag> },
            { title: "健康", render: (_, node) => pct(node.health_score) },
            { title: "可靠性", render: (_, node) => pct(node.reliability_score) },
            { title: "详情", render: (_, node) => <Button size="mini" onClick={() => setActiveNode(node)}>查看</Button> },
          ]}
        />
      </Card>
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
