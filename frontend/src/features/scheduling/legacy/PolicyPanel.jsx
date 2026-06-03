import { SectionTitle } from "./SectionTitle.jsx";

export function PolicyPanel() {
  return (
    <>
      <article className="decision-card">
        <SectionTitle index="02" title="最近决策" compact />
        <div id="decisionPanel" className="decision-list" />
      </article>
      <aside className="insight-stack">
        <article className="model-card">
          <SectionTitle index="03" title="模型推理" compact />
          <div id="modelPanel" className="model-grid" />
        </article>
        <article className="score-card">
          <SectionTitle index="04" title="调度综合权重" compact />
          <div id="fusionPanel" className="fusion-list" />
        </article>
      </aside>
    </>
  );
}
