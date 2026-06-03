import { SectionTitle } from "./SectionTitle.jsx";

export function NodePanel() {
  return (
    <>
      <section className="topology-section">
        <article className="topology-card">
          <SectionTitle index="05" title="GNN 网络拓扑观测">
            <p>按区域、节点与链路状态观察当前推荐路径。</p>
          </SectionTitle>
          <div id="topologyCanvas" className="topology-canvas" />
        </article>
      </section>
      <section className="metrics-grid" id="metricCards" />
      <article className="nodes-card">
        <SectionTitle index="06" title="节点信息" compact />
        <div id="nodesPanel" className="nodes-list" />
      </article>
    </>
  );
}
