import { SectionTitle } from "./SectionTitle.jsx";

export function ChatPanel() {
  return (
    <article className="hermes-console">
      <SectionTitle index="01" title="智能体交互平台">
        <p>LLM 辅助需求理解，控制面工具链完成库存校验、策略生成、仿真和下发保护。</p>
      </SectionTitle>
      <div className="agent-shell">
        <div className="agent-topbar" aria-label="智能体运行状态">
          <div className="agent-status-card"><label>意图理解</label><b id="agentLlmMode">检查中</b><p>LLM 辅助，失败时回退本地规则</p></div>
          <div className="agent-status-card"><label>编排器</label><b id="agentRuntimeMode">ChatRuntime</b><p>多轮状态与工具边界</p></div>
          <div className="agent-status-card"><label>工具链</label><b id="agentToolMode">控制面工具</b><p>查询、策略、仿真、提交</p></div>
        </div>
        <div className="agent-chat-pane">
          <div id="chatLog" className="chat-log">
            <div className="message assistant">
              <b>天钧智能体</b>
              <p>请直接描述业务目标、地域、资源、时延、预算或安全要求。我会先校验节点库存，再给出可审计的策略和仿真结果。</p>
            </div>
          </div>
          <div className="composer">
            <textarea id="intentInput" rows="4" placeholder="输入业务需求、约束或优化反馈。正式下发请使用按钮。" />
            <div className="composer-actions">
              <button id="askButton" className="primary-button">发送</button>
              <button id="stopHermesButton" className="ghost-button danger-soft" disabled>暂停回复</button>
              <button id="submitButton" className="ghost-button danger-soft" disabled>正式下发</button>
              <button id="endTaskButton" className="ghost-button">新会话</button>
            </div>
          </div>
        </div>
        <aside className="agent-workspace" aria-label="当前策略工作区">
          <div className="workspace-head">
            <div>
              <h3>策略工作区</h3>
              <p>只展示当前会话的可操作结果；聊天确认不会直接下发。</p>
            </div>
            <span id="intentSummaryStatus" className="badge">等待需求</span>
          </div>
          <div id="intentSummaryBody" className="workspace-grid">
            <div className="workspace-field"><label>任务</label><b>--</b></div>
            <div className="workspace-field"><label>资源与目标</label><b>--</b></div>
            <div className="workspace-field"><label>推荐节点</label><b>--</b></div>
            <div className="workspace-field"><label>仿真建议</label><b>--</b></div>
          </div>
          <div id="workspaceRisk" className="workspace-risk">等待策略生成后显示风险、确认要求和下发保护状态。</div>
        </aside>
        <section className="tool-trace-panel" aria-label="工具调用轨迹">
          <div className="tool-trace-head"><b>工具调用轨迹</b><span id="toolTraceStatus">等待输入</span></div>
          <div id="toolTraceSteps" className="tool-steps">
            <div className="tool-step"><b>需求理解</b><span>等待</span></div>
            <div className="tool-step"><b>库存校验</b><span>等待</span></div>
            <div className="tool-step"><b>策略生成</b><span>等待</span></div>
            <div className="tool-step"><b>仿真评估</b><span>等待</span></div>
            <div className="tool-step"><b>确认下发</b><span>按钮保护</span></div>
          </div>
        </section>
      </div>
    </article>
  );
}
