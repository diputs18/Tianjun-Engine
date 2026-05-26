from __future__ import annotations

from pathlib import Path


STATIC_DASHBOARD_PATH = Path(__file__).resolve().parents[4] / "html_dashboard" / "dashboard.html"

DASHBOARD_HTML = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>天钧引擎 - 算力网络智能体</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #07111c;
      --bg-2: #0a1623;
      --panel: rgba(12, 28, 44, .88);
      --panel-2: rgba(15, 37, 58, .76);
      --panel-3: rgba(7, 18, 30, .72);
      --line: rgba(125, 196, 255, .18);
      --line-strong: rgba(125, 196, 255, .34);
      --text: #edf7ff;
      --muted: #93a9ba;
      --faint: #678094;
      --cyan: #62d5ff;
      --blue: #4e91ff;
      --green: #68ebb0;
      --yellow: #ffd166;
      --red: #ff6b7a;
      --white: #ffffff;
      --shadow: 0 24px 72px rgba(0, 0, 0, .34);
      --radius: 24px;
      --radius-sm: 16px;
    }

    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      color: var(--text);
      background:
        radial-gradient(circle at 12% 8%, rgba(98, 213, 255, .17), transparent 28%),
        radial-gradient(circle at 84% 8%, rgba(104, 235, 176, .11), transparent 24%),
        linear-gradient(135deg, var(--bg) 0%, var(--bg-2) 52%, #050d15 100%);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      font-size: 14px;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: .78;
      background-image:
        linear-gradient(rgba(125, 196, 255, .045) 1px, transparent 1px),
        linear-gradient(90deg, rgba(125, 196, 255, .045) 1px, transparent 1px);
      background-size: 42px 42px;
      mask-image: linear-gradient(180deg, rgba(0,0,0,.82), transparent 86%);
    }
    button, textarea, input { font: inherit; }
    button { border: 0; cursor: pointer; color: inherit; }
    button:disabled { cursor: not-allowed; opacity: .55; }
    h1, h2, h3, p { margin: 0; }
    a { color: inherit; }

    .shell {
      position: relative;
      width: min(1580px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 26px 0 42px;
    }
    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: end;
      gap: 24px;
      margin-bottom: 18px;
    }
    .eyebrow {
      margin-bottom: 10px;
      color: var(--cyan);
      font-size: 12px;
      letter-spacing: .18em;
      text-transform: uppercase;
      font-weight: 800;
    }
    h1 {
      font-family: "STSong", "Songti SC", "Noto Serif CJK SC", serif;
      font-size: clamp(42px, 5.6vw, 76px);
      line-height: .95;
      letter-spacing: -.06em;
    }
    .subtitle { margin-top: 12px; color: var(--muted); max-width: 850px; line-height: 1.8; }
    .status-deck { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 10px; }
    .status-chip, .pill-button {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 38px;
      padding: 9px 13px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: rgba(255, 255, 255, .055);
      color: var(--muted);
      backdrop-filter: blur(18px);
    }
    .status-chip strong { color: var(--text); }
    .status-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--yellow); box-shadow: 0 0 16px currentColor; }
    .status-dot.ok { background: var(--green); color: var(--green); }
    .status-dot.warn { background: var(--yellow); color: var(--yellow); }
    .status-dot.bad { background: var(--red); color: var(--red); }
    .pill-button { color: var(--text); }
    .pill-button:hover { border-color: var(--cyan); }

    .conversation-stage {
      display: grid;
      grid-template-columns: minmax(600px, 1.18fr) minmax(360px, .82fr);
      gap: 18px;
      align-items: start;
      margin-bottom: 18px;
    }
    .panel {
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: linear-gradient(145deg, rgba(14, 34, 53, .92), rgba(7, 18, 30, .76));
      box-shadow: var(--shadow);
      backdrop-filter: blur(22px);
      overflow: hidden;
    }
    .panel.pad { padding: 20px; }
    .hermes-console {
      min-height: 760px;
      display: flex;
      flex-direction: column;
    }
    .section-title {
      display: flex;
      align-items: flex-start;
      gap: 14px;
      padding: 20px 20px 0;
      margin-bottom: 16px;
    }
    .section-title.compact { align-items: center; padding: 0; margin-bottom: 14px; }
    .section-title .index {
      display: grid;
      place-items: center;
      width: 36px;
      height: 36px;
      flex: 0 0 auto;
      border-radius: 13px;
      color: #06121e;
      font-weight: 900;
      background: linear-gradient(135deg, var(--cyan), var(--green));
      box-shadow: 0 0 26px rgba(98, 213, 255, .22);
    }
    .section-title h2 { font-size: 21px; letter-spacing: -.03em; }
    .section-title p { margin-top: 6px; color: var(--muted); line-height: 1.65; font-size: 13px; }
    .panel-note { margin: -4px 0 12px; color: var(--muted); font-size: 12px; line-height: 1.55; }

    .chat-log {
      flex: 1;
      min-height: 330px;
      max-height: 560px;
      overflow: auto;
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding: 0 20px 14px;
      scrollbar-gutter: stable;
    }
    .empty-chat {
      flex: 1;
      min-height: 300px;
      display: grid;
      place-items: center;
      border: 1px dashed rgba(125, 196, 255, .22);
      border-radius: 20px;
      background: rgba(4, 12, 20, .34);
      color: var(--muted);
      text-align: center;
      line-height: 1.7;
      padding: 20px;
    }
    .message { display: grid; grid-template-columns: 38px minmax(0, 1fr); gap: 10px; align-items: start; }
    .message.user { grid-template-columns: minmax(0, 1fr) 38px; }
    .avatar {
      display: grid;
      place-items: center;
      width: 38px;
      height: 38px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,.055);
      color: var(--cyan);
      font-weight: 900;
      font-size: 12px;
    }
    .message.user .avatar { order: 2; color: #06121e; background: linear-gradient(135deg, var(--cyan), var(--green)); border-color: transparent; }
    .bubble-wrap { max-width: min(760px, 96%); }
    .message.user .bubble-wrap { justify-self: end; order: 1; }
    .bubble-meta { display: flex; gap: 8px; align-items: center; margin-bottom: 5px; color: var(--faint); font-size: 11px; }
    .message.user .bubble-meta { justify-content: flex-end; }
    .bubble {
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 13px 15px;
      background: rgba(255,255,255,.05);
      color: #dcefff;
      line-height: 1.75;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .message.user .bubble { background: rgba(98, 213, 255, .14); border-color: rgba(98, 213, 255, .32); }
    .message.error .bubble { background: rgba(255, 107, 122, .12); border-color: rgba(255, 107, 122, .34); color: #ffdce0; }
    .message.tool .avatar { color: var(--yellow); }
    .message.tool .bubble { background: rgba(255, 209, 102, .075); border-color: rgba(255, 209, 102, .26); color: #ffe8a3; font-size: 12px; }
    .commit-button { background: linear-gradient(135deg, #ffd166, var(--green)); color: #06121e; }
    .commit-button[hidden] { display: none !important; }
    .tag {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 3px 8px;
      border-radius: 999px;
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
    }
    .tag.good { color: var(--green); border-color: rgba(104, 235, 176, .28); background: rgba(104, 235, 176, .08); }
    .tag.warn { color: var(--yellow); border-color: rgba(255, 209, 102, .3); background: rgba(255, 209, 102, .08); }
    .tag.bad { color: var(--red); border-color: rgba(255, 107, 122, .3); background: rgba(255, 107, 122, .08); }
    .tag.primary { color: var(--cyan); border-color: rgba(98, 213, 255, .3); background: rgba(98, 213, 255, .08); }

    .composer {
      margin: 0 20px 14px;
      border: 1px solid var(--line-strong);
      border-radius: 22px;
      padding: 12px;
      background: rgba(4, 12, 20, .58);
    }
    textarea {
      width: 100%;
      min-height: 92px;
      max-height: 190px;
      resize: vertical;
      border: 0;
      outline: 0;
      color: var(--text);
      background: transparent;
      line-height: 1.7;
    }
    textarea::placeholder { color: #607789; }
    .composer-actions { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
    .action-row { display: flex; gap: 10px; flex-wrap: wrap; }
    .primary-button, .ghost-button {
      border: 0;
      border-radius: 14px;
      min-height: 40px;
      padding: 10px 15px;
      font-weight: 900;
      background: linear-gradient(135deg, var(--cyan), var(--green));
      color: #06121e;
    }
    .ghost-button { color: var(--text); background: rgba(255,255,255,.075); border: 1px solid var(--line); }
    .primary-button:hover, .ghost-button:hover { transform: translateY(-1px); border-color: var(--cyan); }
    .hint { color: var(--faint); font-size: 12px; }
    .loading::after {
      content: "";
      display: inline-block;
      width: 12px;
      height: 12px;
      margin-left: 8px;
      border: 2px solid rgba(6,18,30,.45);
      border-top-color: #06121e;
      border-radius: 50%;
      vertical-align: -2px;
      animation: spin .75s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    .intent-summary-panel {
      margin: 0 20px 20px;
      border: 1px solid var(--line);
      background: rgba(6, 18, 29, .42);
      border-radius: 20px;
      padding: 14px;
    }
    .summary-head { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 12px; align-items: center; }
    .summary-head span { color: var(--cyan); font-size: 13px; font-weight: 900; }
    .summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
    .summary-grid div { min-height: 74px; border: 1px solid rgba(125,196,255,.14); background: rgba(15,37,58,.56); border-radius: 14px; padding: 10px; }
    .summary-grid label { display: block; color: var(--muted); font-size: 11px; margin-bottom: 7px; }
    .summary-grid b { display: block; color: var(--text); font-size: 13px; line-height: 1.45; word-break: break-word; }

    .insight-stack { display: grid; gap: 18px; }
    .model-grid, .fusion-list, .decision-list, .nodes-list, .record-list { display: grid; gap: 12px; }
    .model-item, .fusion-row, .decision-item, .node-item, .record-item, .task-column, .component-card, .policy-row {
      border: 1px solid var(--line);
      background: rgba(255,255,255,.045);
      border-radius: 18px;
      padding: 13px;
    }
    .model-item label, .metric-card label, .policy-row label { display: block; color: var(--muted); font-size: 12px; letter-spacing: .06em; text-transform: uppercase; }
    .model-item strong, .metric-card strong { display: block; margin-top: 7px; font-size: 24px; }
    .model-item p, .metric-card p, .decision-item p, .record-item p, .node-meta { color: var(--muted); line-height: 1.55; font-size: 13px; margin-top: 6px; }
    .fusion-row { display: grid; grid-template-columns: 132px 1fr 48px; gap: 10px; align-items: center; }
    .track { height: 8px; border-radius: 999px; background: rgba(255,255,255,.08); overflow: hidden; }
    .bar { height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--cyan), var(--green)); box-shadow: 0 0 18px rgba(98,213,255,.35); }

    .topology-section { display: grid; grid-template-columns: minmax(0, 1.46fr) minmax(350px, .54fr); gap: 18px; margin-bottom: 18px; }
    .topology-canvas {
      min-height: 470px;
      border: 1px solid var(--line);
      border-radius: 22px;
      background:
        radial-gradient(circle at 18% 50%, rgba(98,213,255,.18), transparent 24%),
        radial-gradient(circle at 72% 44%, rgba(104,235,176,.1), transparent 30%),
        linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.015));
      overflow: hidden;
      padding: 10px;
    }
    .topology-canvas svg { width: 100%; height: 370px; display: block; }

    .region-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
    .region-tab { border: 1px solid var(--line); background: rgba(255,255,255,.055); color: var(--muted); border-radius: 999px; padding: 7px 11px; font-size: 12px; font-weight: 900; }
    .region-tab.active { color: #06121e; background: linear-gradient(135deg, var(--cyan), var(--green)); border-color: transparent; }
    .topology-summary { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 8px; padding: 10px 12px; border: 1px solid rgba(125,196,255,.14); border-radius: 14px; background: rgba(7,18,30,.52); color: var(--muted); font-size: 12px; line-height: 1.45; }
    .topology-summary b { color: var(--text); }
    .topology-summary .chips { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
    .topology-summary .chip { border: 1px solid rgba(125,196,255,.16); border-radius: 999px; padding: 4px 8px; background: rgba(255,255,255,.045); color: var(--muted); white-space: nowrap; }

    .metrics-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
    .metric-card { padding: 16px; min-height: 112px; border: 1px solid var(--line); background: linear-gradient(145deg, rgba(14,34,53,.92), rgba(7,18,30,.76)); border-radius: 20px; box-shadow: var(--shadow); }
    .bottom-grid { display: grid; grid-template-columns: minmax(0, .92fr) minmax(0, .92fr) minmax(0, 1.16fr); gap: 18px; align-items: start; }
    .nodes-list { max-height: 680px; overflow: auto; padding-right: 3px; }
    .node-item { display: grid; grid-template-columns: 1fr auto; gap: 10px; }
    .node-item.active { border-color: rgba(98,213,255,.82); background: rgba(98,213,255,.1); }
    .resource-bars { grid-column: 1 / -1; display: grid; gap: 7px; }
    .resource-line { display: grid; grid-template-columns: 58px 1fr 46px; align-items: center; gap: 8px; color: var(--muted); font-size: 12px; }
    .task-board { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .task-column h3 { margin: 0 0 10px; font-size: 14px; }
    .task-pill { padding: 8px; border-radius: 12px; background: rgba(255,255,255,.055); color: #dceeff; margin-top: 7px; font-size: 13px; overflow-wrap: anywhere; }
    .component-list { display: grid; gap: 10px; }
    .component-card b, .policy-row b { display: block; margin-top: 5px; line-height: 1.5; }
    .policy-summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    details.json-panel { border: 1px solid var(--line); border-radius: var(--radius); background: #06111c; color: #dbeafe; overflow: hidden; box-shadow: var(--shadow); }
    details.json-panel summary { cursor: pointer; padding: 14px 16px; border-bottom: 1px solid rgba(255,255,255,.08); font-weight: 900; }
    pre { margin: 0; padding: 16px; max-height: 420px; overflow: auto; white-space: pre-wrap; font-size: 12px; line-height: 1.55; }

    .toast-host { position: fixed; right: 20px; bottom: 20px; display: flex; flex-direction: column; gap: 10px; z-index: 40; }
    .toast { max-width: 430px; border: 1px solid var(--line); border-radius: 14px; background: rgba(12,28,44,.96); box-shadow: var(--shadow); padding: 12px 14px; color: var(--text); }
    .toast.error { border-color: rgba(255,107,122,.35); color: #ffdce0; }

    @media (max-width: 1240px) {
      .hero, .conversation-stage, .topology-section, .bottom-grid { grid-template-columns: 1fr; }
      .metrics-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .hermes-console { min-height: 640px; }
    }
    @media (max-width: 760px) {
      .shell { width: min(100vw - 18px, 1580px); padding-top: 16px; }
      .metrics-grid, .summary-grid, .policy-summary, .task-board { grid-template-columns: 1fr; }
      .status-deck { justify-content: flex-start; }
      .message, .message.user { grid-template-columns: 1fr; }
      .avatar { display: none; }
      .message.user .bubble-wrap { justify-self: stretch; }
      .message.user .bubble-meta { justify-content: flex-start; }
    }
  </style>
</head>
<body>
  <span hidden>天钧算网策略智能体 /policies/draft</span>
  <main class="shell">
    <header class="hero">
      <div>
        <p class="eyebrow">LLM-first · Unified tools · GNN topology aware · LSTM latency prediction</p>
        <h1>天钧引擎</h1>
        <p class="subtitle">面向算力网络场景的智能体控制台。LLM 负责多轮交互，Dashboard 与 Hermes/MCP 共用统一工具层；策略生成、仿真、提交与反馈优化由受控工具链执行。</p>
      </div>
      <section class="status-deck" aria-label="系统状态">
        <div class="status-chip"><span id="healthDot" class="status-dot"></span><span>控制面</span><strong id="healthStatus">检查中</strong></div>
        <div class="status-chip"><span id="modelDot" class="status-dot"></span><span>模型</span><strong id="modelStatus">检查中</strong></div>
        <div class="status-chip"><span id="llmDot" class="status-dot"></span><span>LLM</span><strong id="llmStatus">检查中</strong></div>
        <div class="status-chip"><span>同步</span><strong id="lastSync">--:--:--</strong></div>
        <button id="refreshButton" class="pill-button" type="button">刷新</button>
      </section>
    </header>

    <section class="conversation-stage">
      <article class="panel hermes-console">
        <div class="section-title">
          <span class="index">01</span>
          <div>
            <h2>智能体交互平台</h2>
            <p>输入业务需求或反馈意见。系统会在受控工具边界内完成意图澄清、策略生成和仿真；正式下发必须点击「正式下发」按钮。</p>
          </div>
        </div>
        <div id="chatLog" class="chat-log" aria-live="polite">
          <div id="chatEmpty" class="empty-chat">
            <div>
              <strong>等待输入</strong><br />聊天区不会预填需求，也不会提供快捷话术。请直接输入你的业务目标、资源约束或优化反馈。
            </div>
          </div>
        </div>
        <div class="composer">
          <textarea id="chatInput" rows="4" placeholder="请输入业务需求、资源约束或优化反馈。正式下发请使用按钮。"></textarea>
          <div class="composer-actions">
            <div class="hint">Ctrl + Enter 发送</div>
            <div class="action-row">
              <button id="resetChatButton" class="ghost-button" type="button">新会话</button>
              <button id="commitPolicyButton" class="primary-button commit-button" type="button" hidden disabled>正式下发</button>
              <button id="sendButton" class="primary-button" type="button">发送</button>
            </div>
          </div>
        </div>
        <section class="intent-summary-panel">
          <div class="summary-head"><span>实时策略结果</span><strong id="intentSummaryStatus" class="tag">等待需求</strong></div>
          <div id="intentSummaryBody" class="summary-grid">
            <div><label>任务</label><b>--</b></div>
            <div><label>资源与目标</label><b>--</b></div>
            <div><label>推荐节点</label><b>--</b></div>
            <div><label>仿真建议</label><b>--</b></div>
          </div>
        </section>
      </article>

      <aside class="insight-stack">
        <article class="panel pad">
          <div class="section-title compact"><span class="index">02</span><h2>模型推理</h2></div>
          <div id="modelPanel" class="model-grid"></div>
        </article>
        <article class="panel pad">
          <div class="section-title compact"><span class="index">03</span><h2>融合权重</h2></div>
          <div id="fusionPanel" class="fusion-list"></div>
        </article>
        <article class="panel pad">
          <div class="section-title compact"><span class="index">04</span><h2>策略摘要</h2></div>
          <div id="policySummary" class="policy-summary"></div>
        </article>
        <article class="panel pad">
          <div class="section-title compact"><span class="index">05</span><h2>功能组件</h2></div>
          <div id="componentList" class="component-list"></div>
        </article>
      </aside>
    </section>

    <section class="topology-section">
      <article class="panel pad">
        <div class="section-title compact"><span class="index">06</span><h2>GNN 网络拓扑观测</h2></div>
        <div id="topologyCanvas" class="topology-canvas"></div>
      </article>
      <article class="panel pad">
        <div class="section-title compact"><span class="index">07</span><h2>最近决策</h2></div>
        <div id="decisionPanel" class="decision-list"></div>
      </article>
    </section>

    <section class="metrics-grid" id="metricCards" aria-label="指标概览"></section>

    <section class="bottom-grid">
      <article class="panel pad">
        <div class="section-title compact"><span class="index">08</span><h2>节点信息</h2></div>
        <p class="panel-note">启动 sim-backend 后，这里显示配置文件注册的仿真节点；它们不是物理机器。未启动仿真或真实 Agent 时应为空。</p>
        <div id="nodesPanel" class="nodes-list"></div>
      </article>
      <article class="panel pad">
        <div class="section-title compact"><span class="index">09</span><h2>任务流转</h2></div>
        <div id="tasksPanel" class="task-board"></div>
      </article>
      <article class="panel pad">
        <div class="section-title compact"><span class="index">10</span><h2>执行回放</h2></div>
        <div id="recordsPanel" class="record-list"></div>
      </article>
    </section>

    <details class="json-panel" style="margin-top:18px;">
      <summary>策略与仿真 JSON</summary>
      <pre id="policyJson">{}</pre>
    </details>
  </main>
  <div id="toastHost" class="toast-host" aria-live="polite"></div>

  <script>
    const state = { sessionId: null, latestPolicy: null, latestSimulation: null, latestReport: null, sending: false, committing: false, hasMessages: false, pendingCommitPolicyId: null, toolBubble: null, toolSteps: [], topologyRegion: "all" };
    const $ = (id) => document.getElementById(id);
    const fmtNumber = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
    const nowTime = () => new Date().toLocaleTimeString("zh-CN", { hour12: false });
    const asJson = (value) => JSON.stringify(value ?? {}, null, 2);

    const labels = {
      pending: "待调度", running: "运行中", succeeded: "已成功", failed: "已失败",
      performance: "性能", completion: "完成时间", cost: "成本", reliability: "可靠性",
      balance: "负载均衡", fragmentation: "碎片化", locality: "地域匹配", network: "网络质量", security: "安全",
      latency_history: "LSTM 时延", jitter: "时延抖动", node_load: "节点负载", bandwidth_utilization: "带宽可用性", gnn_topology: "GNN 拓扑",
      cpu: "CPU", memory: "内存", gpu: "GPU", storage: "存储"
    };
    const regions = { shanghai: "上海", beijing: "北京", hangzhou: "杭州", shenzhen: "深圳", guangzhou: "广州", dongguan: "东莞", chengdu: "成都", wuhan: "武汉", huizhou: "惠州", zhuhai: "珠海", foshan: "佛山", zhongshan: "中山" };

    function escapeHtml(value) {
      return String(value ?? "-")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }
    function display(value, suffix = "") {
      if (value === null || value === undefined || value === "") return "--";
      const number = Number(value);
      if (Number.isFinite(number)) return `${fmtNumber.format(number)}${suffix}`;
      return `${value}${suffix}`;
    }
    function percent(value, digits = 1) {
      const number = Number(value ?? 0) * 100;
      return `${number.toFixed(digits)}%`;
    }
    function displayKey(key) { return labels[String(key ?? "").toLowerCase()] || String(key ?? "-").replaceAll("_", " "); }
    function displayRegion(region) { return regions[String(region ?? "").toLowerCase()] || String(region ?? "--"); }
    function displayCommitRecommendation(value) {
      return {
        safe_to_commit: "可正式下发",
        review_before_commit: "可下发，需先确认风险",
        do_not_commit: "不可正式下发"
      }[String(value ?? "")] || "等待仿真结果";
    }
    function latestDecision(report = state.latestReport) {
      const decisions = report?.recent_decisions || [];
      if (decisions.length) return decisions[decisions.length - 1];
      return state.latestPolicy?.decision || null;
    }
    function effectiveDecision() {
      const policyNode = state.latestPolicy?.selected_compute?.node_id;
      if (!policyNode) return latestDecision();
      return latestDecision() || null;
    }
    function resourceUtil(node, key) {
      const live = Number(node.runtime_utilization?.[key]);
      if (Number.isFinite(live) && live > 0) return Math.max(0, Math.min(1, live));
      const total = Number(node.capacity?.[key] ?? 0);
      const available = Number(node.available?.[key] ?? 0);
      if (total <= 0) return 0;
      return Math.max(0, Math.min(1, (total - available) / total));
    }
    function toast(message, kind = "") {
      const node = document.createElement("div");
      node.className = `toast ${kind}`;
      node.textContent = message;
      $("toastHost").appendChild(node);
      setTimeout(() => node.remove(), 3600);
    }
    async function getJson(path) {
      const response = await fetch(path, { headers: { "Accept": "application/json" }});
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }
    async function postJson(path, payload) {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }

    function addMessage(role, content, action = "") {
      const empty = $("chatEmpty");
      if (empty) empty.remove();
      state.hasMessages = true;
      const stream = $("chatLog");
      const wrapper = document.createElement("div");
      const type = role === "user" ? "user" : role === "error" ? "error" : role === "tool" ? "tool" : "assistant";
      wrapper.className = `message ${type}`;
      const avatar = role === "user" ? "ME" : role === "error" ? "ERR" : role === "tool" ? "TOOL" : "AI";
      const roleName = role === "user" ? "你" : role === "error" ? "异常" : role === "tool" ? "工具调用" : "天钧智能体";
      wrapper.innerHTML = `
        <div class="avatar">${escapeHtml(avatar)}</div>
        <div class="bubble-wrap">
          <div class="bubble-meta"><span>${escapeHtml(roleName)}</span><span>${nowTime()}</span>${action ? `<span class="tag primary">${escapeHtml(action)}</span>` : ""}</div>
          <div class="bubble">${escapeHtml(content)}</div>
        </div>`;
      stream.appendChild(wrapper);
      stream.scrollTop = stream.scrollHeight;
      return wrapper.querySelector(".bubble");
    }
    function resetToolProgress() {
      state.toolBubble = null;
      state.toolSteps = [];
    }
    function updateToolProgress(event) {
      const label = event.label || displayToolName(event.tool || "tool");
      if (event.type === "tool_start") state.toolSteps.push(`${label}…`);
      if (event.type === "tool_done") {
        const pending = `${label}…`;
        const done = `${label}✓`;
        const idx = state.toolSteps.lastIndexOf(pending);
        if (idx >= 0) state.toolSteps[idx] = done;
        else state.toolSteps.push(done);
      }
      const content = `工具链：${state.toolSteps.join(" → ")}`;
      if (!state.toolBubble) state.toolBubble = addMessage("tool", content, "tools");
      else updateStreamingBubble(state.toolBubble, content);
    }
    function addToolEvent(tool, text, phase = "") {
      updateToolProgress({ type: phase === "start" ? "tool_start" : "tool_done", tool, label: displayToolName(tool), summary: text });
    }
    function addToolSummary(tools) {
      const list = Array.isArray(tools) ? tools : [];
      if (!list.length) return;
      resetToolProgress();
      for (const item of list) updateToolProgress({ type: "tool_done", tool: item.tool, label: displayToolName(item.tool || "tool"), summary: item.summary });
    }
    function displayToolName(name) {
      const labels = {
        get_cluster_state: "查询集群状态",
        start_requirement_dialogue: "需求澄清",
        continue_requirement_dialogue: "更新需求",
        draft_compute_network_policy: "生成策略",
        simulate_policy: "策略仿真",
        commit_policy: "正式下发",
        optimize_policy_from_feedback: "优化策略",
      };
      return labels[name] || name;
    }
    function updateStreamingBubble(bubble, content) {
      bubble.textContent = content;
      const stream = $("chatLog");
      stream.scrollTop = stream.scrollHeight;
    }
    function setPill(dotId, textId, status, kind) {
      const dot = $(dotId);
      dot.className = `status-dot ${kind}`;
      $(textId).textContent = status;
    }

    function emptyCard(text) { return `<div class="record-item"><p>${escapeHtml(text)}</p></div>`; }
    function metricCard(label, value, sub) {
      return `<article class="metric-card"><label>${escapeHtml(label)}</label><strong>${escapeHtml(value)}</strong><p>${escapeHtml(sub)}</p></article>`;
    }
    function renderMetrics(report) {
      const metrics = report.metrics || {};
      const totals = report.totals || {};
      const active = totals.running_tasks ?? totals.leased_tasks ?? 0;
      const cards = [
        ["成功率", percent(metrics.success_rate ?? 0), `SLA ${percent(metrics.sla_rate ?? 0)}`],
        ["稳定时延", `${display(metrics.average_stable_latency_ms, " ms")}`, "平均稳定化结果"],
        ["融合评分", display(metrics.average_fusion_score), "LSTM + GNN + 资源"],
        ["确定化置信度", percent(metrics.average_deterministic_confidence ?? 0), "网络不确定性压缩"],
        ["待调度", display(totals.pending_tasks), `${display(active)} 个活跃任务`],
        ["完成尝试", display(totals.completed_attempts), `${display(totals.succeeded_attempts)} 成功`],
      ];
      $("metricCards").innerHTML = cards.map(([a, b, c]) => metricCard(a, b, c)).join("");
    }
    function renderModel(report) {
      const runtime = report.model_runtime || {};
      const decision = latestDecision(report);
      const snap = decision?.network_snapshot || {};
      const pred = snap.model_prediction || runtime.latest_prediction || {};
      const gnnUsable = pred.gnn_applicable !== false && pred.gnn_stability_score !== undefined && pred.gnn_stability_score !== null;
      const gnnSub = pred.gnn_applicable === false
        ? `已排除分布外输出 · 原始 ${percent(pred.gnn_raw_output ?? 0)}`
        : "GraphSAGE 拓扑评分";
      const items = [
        ["运行状态", runtime.status || "unknown", runtime.detail || "等待模型运行时"],
        ["LSTM 预测", pred.lstm_latency_ms ? `${display(pred.lstm_latency_ms, " ms")}` : "暂无", snap.latency_predictor || "等待决策"],
        ["GNN 稳定", gnnUsable ? percent(pred.gnn_stability_score) : (pred.gnn_applicable === false ? "已降级" : "暂无"), gnnSub],
        ["GNN 时延", pred.gnn_latency_ms ? `${display(pred.gnn_latency_ms, " ms")}` : "暂无", "拓扑嵌入修正结果"],
      ];
      $("modelPanel").innerHTML = items.map(([label, value, sub]) => `<div class="model-item"><label>${escapeHtml(label)}</label><strong>${escapeHtml(value)}</strong><p>${escapeHtml(sub)}</p></div>`).join("");
    }
    function renderFusion(report) {
      const decision = latestDecision(report);
      const snap = decision?.network_snapshot || {};
      const weights = snap.feature_weights || { latency_history: .32, jitter: .20, node_load: .18, bandwidth_utilization: .12, gnn_topology: .18 };
      const features = snap.fusion_features || {};
      $("fusionPanel").innerHTML = Object.entries(weights).map(([key, weight]) => {
        const value = Number(features[key] ?? weight ?? 0);
        return `<div class="fusion-row"><span>${escapeHtml(displayKey(key))}</span><div class="track"><div class="bar" style="width:${Math.max(4, Math.min(100, value * 100))}%"></div></div><b>${percent(weight, 0)}</b></div>`;
      }).join("");
    }
    function renderTopology(report) {
      const nodes = report.nodes || [];
      const decision = latestDecision(report);
      const selected = state.latestPolicy?.selected_compute?.node_id || decision?.node_id;
      const snap = decision?.network_snapshot || {};
      const canvas = $("topologyCanvas");
      if (!nodes.length) { canvas.innerHTML = emptyCard("等待节点注册。"); return; }

      const grouped = new Map();
      for (const node of nodes) {
        const region = String(node.region || "unknown").toLowerCase();
        if (!grouped.has(region)) grouped.set(region, []);
        grouped.get(region).push(node);
      }
      const regionsSorted = Array.from(grouped.keys()).sort((a, b) => displayRegion(a).localeCompare(displayRegion(b), "zh-CN"));
      if (state.topologyRegion !== "all" && !grouped.has(state.topologyRegion)) state.topologyRegion = "all";
      const visibleNodes = state.topologyRegion === "all" ? nodes : (grouped.get(state.topologyRegion) || []);
      const selectedRegion = selected ? String((nodes.find((node) => node.node_id === selected) || {}).region || "").toLowerCase() : "";
      const width = 980, height = 420, cx = 490, cy = 210, radius = Math.max(92, Math.min(160, 48 + visibleNodes.length * 10));
      const lines = [];
      const circles = [];
      visibleNodes.forEach((node, index) => {
        const angle = (-90 + index * (360 / Math.max(1, visibleNodes.length))) * Math.PI / 180;
        const x = cx + Math.cos(angle) * radius;
        const y = cy + Math.sin(angle) * radius;
        const active = node.node_id === selected;
        const health = Number(node.health_score ?? 0.8);
        const color = active ? "#62d5ff" : health > .9 ? "#68ebb0" : health > .65 ? "#ffd166" : "#ff6b7a";
        lines.push(`<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="${active ? "#62d5ff" : "rgba(125,196,255,.22)"}" stroke-width="${active ? 4 : 2}" stroke-dasharray="8 10" />`);
        circles.push(`
          <g>
            <circle cx="${x}" cy="${y}" r="${active ? 38 : 30}" fill="rgba(7,18,30,.94)" stroke="${color}" stroke-width="${active ? 4 : 2}" />
            <text x="${x}" y="${y - 5}" text-anchor="middle" fill="#edf7ff" font-size="11" font-weight="800">${escapeHtml(node.node_id).slice(0, 18)}</text>
            <text x="${x}" y="${y + 13}" text-anchor="middle" fill="#93a9ba" font-size="11">${escapeHtml(displayRegion(node.region))}</text>
          </g>`);
      });
      const tabs = [`<button class="region-tab ${state.topologyRegion === "all" ? "active" : ""}" data-region="all">全部 · ${nodes.length}</button>`]
        .concat(regionsSorted.map((region) => `<button class="region-tab ${state.topologyRegion === region ? "active" : ""}" data-region="${escapeHtml(region)}">${escapeHtml(displayRegion(region))} · ${(grouped.get(region) || []).length}</button>`))
        .join("");
      const selectedNode = selected ? nodes.find((node) => node.node_id === selected) : null;
      const onlineCount = visibleNodes.filter((node) => node.online).length;
      const gpuCount = visibleNodes.reduce((sum, node) => sum + Number(node.capacity?.gpu || 0), 0);
      const cpuCount = visibleNodes.reduce((sum, node) => sum + Number(node.capacity?.cpu || 0), 0);
      const summaryTitle = state.topologyRegion === "all" ? `全部地域 · ${visibleNodes.length} 节点` : `${displayRegion(state.topologyRegion)} · ${visibleNodes.length} 节点`;
      const selectedSummary = selectedNode ? `当前策略节点：${selectedNode.node_id} · ${displayRegion(selectedNode.region)} · ${selectedNode.online ? "在线" : "离线"}` : "当前策略节点：等待策略";
      canvas.innerHTML = `
        <div class="region-tabs">${tabs}</div>
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="GNN 网络拓扑">
          <defs><radialGradient id="coreGlow"><stop offset="0%" stop-color="#62d5ff" stop-opacity=".35"/><stop offset="100%" stop-color="#62d5ff" stop-opacity="0"/></radialGradient></defs>
          <rect x="8" y="8" width="${width - 16}" height="${height - 16}" rx="24" fill="rgba(4,12,20,.2)" stroke="rgba(125,196,255,.1)" />
          <circle cx="${cx}" cy="${cy}" r="118" fill="url(#coreGlow)" />
          ${lines.join("")}
          ${circles.join("")}
          <circle cx="${cx}" cy="${cy}" r="54" fill="rgba(7,18,30,.96)" stroke="#62d5ff" stroke-width="3" />
          <text x="${cx}" y="${cy - 8}" text-anchor="middle" fill="#edf7ff" font-size="17" font-weight="900">${state.topologyRegion === "all" ? "Tianjun" : escapeHtml(displayRegion(state.topologyRegion))}</text>
          <text x="${cx}" y="${cy + 16}" text-anchor="middle" fill="#93a9ba" font-size="12">${state.topologyRegion === "all" ? "算网策略核心" : "地域节点视图"}</text>
          <text x="28" y="40" fill="#93a9ba" font-size="13">当前选择：${escapeHtml(selected || "等待策略")}</text>
          <text x="28" y="64" fill="#93a9ba" font-size="13">选择地域：${escapeHtml(state.topologyRegion === "all" ? "全部" : displayRegion(state.topologyRegion))}</text>
          <text x="28" y="88" fill="#93a9ba" font-size="13">稳定时延：${snap.stable_latency_ms ? `${display(snap.stable_latency_ms, " ms")}` : "暂无"}</text>
          <text x="28" y="112" fill="#93a9ba" font-size="13">GNN 拓扑：${percent(snap.fusion_features?.gnn_topology ?? 0)}</text>
          ${selectedRegion && state.topologyRegion !== selectedRegion ? `<text x="28" y="136" fill="#ffd166" font-size="13">提示：当前策略节点位于 ${escapeHtml(displayRegion(selectedRegion))}</text>` : ""}
        </svg>
        <div class="topology-summary">
          <span><b>${escapeHtml(summaryTitle)}</b><br/>${escapeHtml(selectedSummary)}</span>
          <span class="chips">
            <span class="chip">在线 ${onlineCount}</span>
            <span class="chip">CPU ${display(cpuCount)}</span>
            <span class="chip">GPU ${display(gpuCount)}</span>
          </span>
        </div>`;
      canvas.querySelectorAll(".region-tab").forEach((button) => {
        button.addEventListener("click", () => {
          state.topologyRegion = button.getAttribute("data-region") || "all";
          renderTopology(state.latestReport || report);
        });
      });
    }

    function renderDecisions(report) {
      const decisions = (report.recent_decisions || []).slice().reverse().slice(0, 6);
      $("decisionPanel").innerHTML = decisions.length ? decisions.map((decision) => {
        const snap = decision.network_snapshot || {};
        return `<div class="decision-item"><b>${escapeHtml(decision.task_id)} -> ${escapeHtml(decision.node_id)}</b><p>融合评分 ${display(snap.feature_fusion_score)}，稳定时延 ${display(snap.stable_latency_ms, " ms")}，GNN ${percent(snap.fusion_features?.gnn_topology ?? 0)}。</p></div>`;
      }).join("") : emptyCard("暂无调度决策。");
    }
    function renderNodes(report) {
      const nodes = report.nodes || [];
      const selected = state.latestPolicy?.selected_compute?.node_id || latestDecision(report)?.node_id;
      $("nodesPanel").innerHTML = nodes.length ? nodes.map((node) => {
        const bars = ["cpu", "memory", "gpu", "storage"].map((key) => {
          const used = resourceUtil(node, key);
          return `<div class="resource-line"><span>${displayKey(key)}</span><div class="track"><div class="bar" style="width:${Math.max(4, used * 100)}%"></div></div><b>${percent(used, 0)}</b></div>`;
        }).join("");
        const labels = node.labels || [];
        const isSim = labels.includes("simulation") || labels.includes("simulated-node");
        const source = isSim ? "仿真节点" : "真实节点";
        const onlineText = node.online ? (isSim ? "仿真在线" : "在线") : "离线";
        return `<div class="node-item ${node.node_id === selected ? "active" : ""}"><div><b>${escapeHtml(node.node_id)}</b><div class="node-meta">${displayRegion(node.region)} · ${source} · 健康 ${percent(node.health_score ?? 0)} · 可靠 ${percent(node.reliability_score ?? 0)}</div></div><span class="tag ${node.online ? "good" : "bad"}">${onlineText}</span><div class="resource-bars">${bars}</div></div>`;
      }).join("") : emptyCard("暂无节点。");
    }
    function renderTasks(report) {
      const statuses = report.task_statuses || {};
      const groups = { pending: [], running: [], succeeded: [], failed: [] };
      Object.entries(statuses).forEach(([task, status]) => { if (groups[status]) groups[status].push(task); });
      $("tasksPanel").innerHTML = Object.entries(groups).map(([status, tasks]) => `<div class="task-column"><h3>${displayKey(status)} · ${tasks.length}</h3>${tasks.slice(0, 6).map((task) => `<div class="task-pill">${escapeHtml(task)}</div>`).join("") || `<div class="task-pill">暂无</div>`}</div>`).join("");
    }
    function renderRecords(report) {
      const activeRuns = (report.active_runs || []).slice().reverse();
      const activeHtml = activeRuns.map((run) => {
        const metrics = run.metrics || {};
        const util = metrics.simulated_utilization || {};
        const utilText = Object.keys(util).length ? ` · GPU ${percent(util.gpu ?? 0, 0)} · CPU ${percent(util.cpu ?? 0, 0)}` : "";
        const qpsText = metrics.target_qps !== undefined ? ` · QPS ${display(metrics.achieved_qps)} / ${display(metrics.target_qps)}` : "";
        const latencyText = metrics.latency_p99_ms !== undefined ? ` · P99 ${display(metrics.latency_p99_ms, " ms")}` : "";
        const plannedText = metrics.planned_execution_seconds !== undefined ? ` · 计划 ${display(metrics.planned_execution_seconds, "s")}` : "";
        return `<div class="record-item active"><b>${escapeHtml(run.task_id)} @ ${escapeHtml(run.node_id)}</b><p>运行中 · 阶段 ${escapeHtml(run.stage || "running")} · 进度 ${percent(run.progress ?? 0, 0)}${utilText}${plannedText}${latencyText}${qpsText}</p></div>`;
      }).join("");
      const records = (report.recent_records || []).slice().reverse().slice(0, 7);
      const recordHtml = records.map((record) => {
        const sim = record.metadata?.simulation || {};
        const metrics = sim.metrics || {};
        const lifecycle = (sim.lifecycle_events || []).map((event) => `${event.stage}:${event.status}`).join(" → ");
        const detail = sim.backend
          ? `${metrics.planned_execution_seconds !== undefined ? ` · 计划 ${display(metrics.planned_execution_seconds, "s")}` : ""}${metrics.target_qps !== undefined ? ` · QPS ${display(metrics.achieved_qps)} / ${display(metrics.target_qps)}` : ""}${metrics.latency_p99_ms !== undefined ? ` · P99 ${display(metrics.latency_p99_ms, " ms")}` : ""}${metrics.replicas_actual !== undefined ? ` · 副本 ${display(metrics.replicas_actual)}` : ""}`
          : "";
        const compliance = sim.compliance ? ` · 合规 ${sim.compliance.passed ? "通过" : "失败"}` : "";
        const lifecycleLine = lifecycle ? `<p>阶段：${escapeHtml(lifecycle)}</p>` : "";
        return `<div class="record-item"><b>${escapeHtml(record.task_id)} @ ${escapeHtml(record.node_id)}</b><p>${record.success ? "执行成功" : "执行失败"} · 时长 ${display(record.actual_duration)} tick · 成本 ${display(record.cost)} · 网络延迟 ${display(record.network_delay_ticks)} tick${escapeHtml(detail + compliance)}</p>${lifecycleLine}</div>`;
      }).join("");
      $("recordsPanel").innerHTML = (activeHtml + recordHtml) || emptyCard("暂无执行记录。启动 sim-backend 并提交任务后，这里会显示阶段化执行进度。");
    }
    function renderPolicy(policy, simulation = null) {
      state.latestPolicy = policy || null;
      state.latestSimulation = simulation || null;
      if (!policy) {
        $("policySummary").innerHTML = emptyCard("暂无策略。输入需求后将展示策略摘要。");
        $("componentList").innerHTML = emptyCard("暂无组件。策略生成后展示算力、网络、QoS、安全和执行组件。");
        $("policyJson").textContent = "{}";
        updateIntentSummary(null, null);
        return;
      }
      const effect = policy.expected_effect || {};
      const latency = effect.latency || {};
      const cost = effect.cost || {};
      const sq = effect.service_quality || {};
      const security = effect.security || {};
      const load = effect.load || {};
      const compute = policy.selected_compute || {};
      const network = policy.selected_network || {};
      const diagnostics = simulation?.diagnostics || {};
      const risks = policy.explanation?.risks || [];
      $("policySummary").innerHTML = [
        ["算力节点", compute.node_id || compute.name || "--"],
        ["目标地域", compute.region || network.target_region || "--"],
        ["稳定时延", `${display(latency.expected_ms, " ms")} / 目标 ${display(latency.target_ms, " ms")}`],
        ["预计成本", `${display(cost.expected_cost)} / 预算 ${display(cost.budget_limit)}`],
        ["服务质量", `SLA ${display(sq.sla_probability)}，负载 ${display(load.projected_load)}`],
        ["安全等级", `${security.security_level || "--"}，评分 ${display(security.security_score)}`],
        ["风险", risks.length ? risks.join("；") : "暂无显式风险"],
        ["下发建议", displayCommitRecommendation(diagnostics.commit_recommendation)],
      ].map(([label, value]) => `<div class="policy-row"><label>${escapeHtml(label)}</label><b>${escapeHtml(value)}</b></div>`).join("");
      const components = policy.functional_components || [];
      $("componentList").innerHTML = components.length ? components.map((component) => {
        const subtitle = [component.name, component.region, component.target_region, component.mode].filter(Boolean).join(" / ") || "由策略引擎生成";
        return `<div class="component-card"><span class="tag primary">${escapeHtml(component.type || "component")}</span><b>${escapeHtml(subtitle)}</b></div>`;
      }).join("") : emptyCard("策略未返回组件清单。");
      $("policyJson").textContent = asJson({ policy, simulation });
      updateIntentSummary(policy, simulation);
      if (policy && !["failed", "committed"].includes(policy.status) && simulation?.feasible) state.pendingCommitPolicyId = policy.policy_id;
      updateCommitButton();
      if (state.latestReport) {
        renderTopology(state.latestReport);
        renderNodes(state.latestReport);
      }
    }
    function updateIntentSummary(policy, simulation) {
      const status = $("intentSummaryStatus");
      if (!policy) {
        status.className = "tag";
        status.textContent = "等待需求";
        $("intentSummaryBody").innerHTML = `<div><label>任务</label><b>--</b></div><div><label>资源与目标</label><b>--</b></div><div><label>推荐节点</label><b>--</b></div><div><label>仿真建议</label><b>--</b></div>`;
        return;
      }
      status.className = `tag ${policy.status === "failed" ? "bad" : "good"}`;
      status.textContent = policy.status || "drafted";
      const req = policy.requirement || {};
      const res = policy.resource_config || {};
      const compute = policy.selected_compute || {};
      const latency = policy.expected_effect?.latency || {};
      const diagnostics = simulation?.diagnostics || {};
      $("intentSummaryBody").innerHTML = `
        <div><label>任务</label><b>${escapeHtml(req.workload_type || policy.policy_id || "--")}</b></div>
        <div><label>资源与目标</label><b>CPU ${display(res.cpu_cores)} / MEM ${display(res.memory_gb, "G")} / GPU ${display(res.gpu_count)} / ${display(latency.target_ms, "ms")}</b></div>
        <div><label>推荐节点</label><b>${escapeHtml(compute.node_id || "--")}</b></div>
        <div><label>下发建议</label><b>${escapeHtml(displayCommitRecommendation(diagnostics.commit_recommendation))}</b></div>`;
    }
    async function refresh() {
      try {
        const [health, report] = await Promise.all([getJson("/health"), getJson("/report")]);
        state.latestReport = report;
        setPill("healthDot", "healthStatus", health.status || "ok", health.status === "ok" ? "ok" : "warn");
        const modelStatus = health.model_runtime?.status || "unknown";
        setPill("modelDot", "modelStatus", modelStatus, modelStatus === "loaded" ? "ok" : "warn");
        const llmEnabled = Boolean(health.chat_runtime?.llm?.enabled);
        const llmMode = llmEnabled ? "意图辅助已启用" : "本地规则";
        setPill("llmDot", "llmStatus", llmMode, llmEnabled ? "ok" : "warn");
        $("lastSync").textContent = nowTime();
        renderMetrics(report);
        renderModel(report);
        renderFusion(report);
        renderTopology(report);
        renderDecisions(report);
        renderNodes(report);
        renderTasks(report);
        renderRecords(report);
      } catch (error) {
        setPill("healthDot", "healthStatus", "error", "bad");
        toast(`刷新失败：${error.message}`, "error");
      }
    }
    function setSending(isSending) {
      state.sending = isSending;
      const button = $("sendButton");
      button.disabled = isSending;
      button.classList.toggle("loading", isSending);
      button.textContent = isSending ? "处理中" : "发送";
    }
    function updateCommitButton() {
      const button = $("commitPolicyButton");
      const policyId = state.pendingCommitPolicyId || state.latestPolicy?.policy_id || null;
      const canCommit = Boolean(policyId && state.sessionId && state.latestPolicy && !["failed", "committed"].includes(state.latestPolicy.status) && !state.committing);
      button.hidden = !canCommit;
      button.disabled = !canCommit;
      button.classList.toggle("loading", state.committing);
      button.textContent = state.committing ? "下发中" : "正式下发";
    }
    function applyChatResult(result) {
      state.sessionId = result.session?.session_id || state.sessionId;
      if (result.commit_policy_id) state.pendingCommitPolicyId = result.commit_policy_id;
      if (result.requires_user_button && result.commit_policy_id) state.pendingCommitPolicyId = result.commit_policy_id;
      const artifacts = result.artifacts || {};
      if (artifacts.policy) renderPolicy(artifacts.policy, artifacts.simulation || null);
      if (artifacts.optimization?.policy) renderPolicy(artifacts.optimization.policy, artifacts.simulation || null);
      if (artifacts.commit) {
        state.pendingCommitPolicyId = null;
        if (artifacts.commit.policy) renderPolicy(artifacts.commit.policy, state.latestSimulation || null);
        $("policyJson").textContent = asJson({ commit: artifacts.commit, policy: state.latestPolicy, simulation: state.latestSimulation });
      }
      updateCommitButton();
    }
    async function readEventStream(response, onEvent) {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      function consumeBlock(block) {
        const dataLines = [];
        for (const raw of block.split("\n")) {
          const line = raw.trimEnd();
          if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
        }
        if (!dataLines.length) return;
        const payload = dataLines.join("\n");
        if (!payload || payload === "[DONE]") return;
        onEvent(JSON.parse(payload));
      }
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let index;
        while ((index = buffer.indexOf("\n\n")) >= 0) {
          const block = buffer.slice(0, index);
          buffer = buffer.slice(index + 2);
          consumeBlock(block);
        }
      }
      if (buffer.trim()) consumeBlock(buffer);
    }
    async function sendChat() {
      const input = $("chatInput");
      const message = input.value.trim();
      if (!message || state.sending) return;
      addMessage("user", message);
      input.value = "";
      setSending(true);
      let assistantBubble = null;
      let streamedText = "";
      try {
        const endpoint = state.sessionId
          ? `/chat/sessions/${encodeURIComponent(state.sessionId)}/messages/stream`
          : "/chat/sessions/stream";
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
          body: JSON.stringify({ message }),
        });
        if (!response.ok || !response.body) throw new Error(await response.text());
        let finalResult = null;
        resetToolProgress();
        await readEventStream(response, (event) => {
          if (event.type === "session") {
            state.sessionId = event.session?.session_id || state.sessionId;
            if (event.commit_policy_id) state.pendingCommitPolicyId = event.commit_policy_id;
            updateCommitButton();
          } else if (event.type === "tools") {
            addToolSummary(event.tools || []);
          } else if (event.type === "tool_start" || event.type === "tool_done") {
            updateToolProgress(event);
          } else if (event.type === "tool_result") {
            updateToolProgress({ type: "tool_done", tool: event.tool || "tool", summary: event.summary || "done" });
          } else if (event.type === "artifacts") {
            const artifacts = event.artifacts || {};
            if (artifacts.policy) renderPolicy(artifacts.policy, artifacts.simulation || null);
            if (artifacts.optimization?.policy) renderPolicy(artifacts.optimization.policy, artifacts.simulation || null);
          } else if (event.type === "error") {
            throw new Error(event.message || "stream error");
          } else if (event.type === "assistant_delta") {
            streamedText += event.delta || "";
            if (!assistantBubble) assistantBubble = addMessage("assistant", "", "streaming");
            updateStreamingBubble(assistantBubble, streamedText);
          } else if (event.type === "done") {
            finalResult = event.result || null;
          }
        });
        if (finalResult) {
          if (!assistantBubble && finalResult.message) assistantBubble = addMessage("assistant", finalResult.message, finalResult.action || "streaming");
          applyChatResult(finalResult);
        }
        await refresh();
      } catch (error) {
        updateStreamingBubble(assistantBubble, `请求失败：${error.message}`);
        toast("聊天请求失败，请检查控制面、LLM 密钥或网络连接。", "error");
      } finally {
        setSending(false);
      }
    }
    async function commitLatestPolicy() {
      if (state.committing) return;
      const policyId = state.pendingCommitPolicyId || state.latestPolicy?.policy_id;
      if (!state.sessionId || !policyId) { toast("当前没有可提交的策略", "error"); return; }
      state.committing = true;
      updateCommitButton();
      try {
        const result = await postJson(`/chat/sessions/${encodeURIComponent(state.sessionId)}/commit`, { policy_id: policyId });
        addToolSummary((result.tool_trace_delta || []).map((trace) => ({ tool: trace.tool, summary: trace.result_summary })));
        addMessage("assistant", result.message || "策略已提交。", result.action || "commit_policy");
        applyChatResult(result);
        await refresh();
      } catch (error) {
        addMessage("error", `提交失败：${error.message}`);
        toast("提交失败，请检查策略状态或控制面。", "error");
      } finally {
        state.committing = false;
        updateCommitButton();
      }
    }
    function resetChat() {
      state.sessionId = null;
      state.latestPolicy = null;
      state.latestSimulation = null;
      state.hasMessages = false;
      state.pendingCommitPolicyId = null;
      $("chatLog").innerHTML = `<div id="chatEmpty" class="empty-chat"><div><strong>等待输入</strong><br />聊天区不会预填需求，也不会提供快捷话术。请直接输入你的业务目标、资源约束或优化反馈。</div></div>`;
      renderPolicy(null, null);
      updateCommitButton();
      toast("新会话已创建");
    }

    document.addEventListener("DOMContentLoaded", () => {
      $("sendButton").addEventListener("click", sendChat);
      $("refreshButton").addEventListener("click", refresh);
      $("resetChatButton").addEventListener("click", resetChat);
      $("commitPolicyButton").addEventListener("click", commitLatestPolicy);
      $("chatInput").addEventListener("keydown", (event) => { if (event.ctrlKey && event.key === "Enter") sendChat(); });
      renderPolicy(null, null);
      refresh();
      setInterval(refresh, 5000);
    });
  </script>
</body>
</html>
"""


def render_dashboard_html() -> str:
    if STATIC_DASHBOARD_PATH.exists():
        return STATIC_DASHBOARD_PATH.read_text(encoding="utf-8")
    return DASHBOARD_HTML
