import { SectionTitle } from "./SectionTitle.jsx";

export function ReportPanel() {
  return (
    <article className="records-card">
      <SectionTitle index="08" title="执行回放" compact />
      <div id="recordsPanel" className="record-list" />
    </article>
  );
}
