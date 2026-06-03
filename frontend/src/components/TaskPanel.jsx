import { SectionTitle } from "./SectionTitle.jsx";

export function TaskPanel() {
  return (
    <article className="tasks-card">
      <SectionTitle index="07" title="任务流转" compact />
      <div id="tasksPanel" className="task-board" />
    </article>
  );
}
