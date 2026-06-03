export function StatusHeader() {
  return (
    <header className="hero">
      <div>
        <p className="eyebrow">Hermes first / GNN topology aware / LSTM latency prediction</p>
        <h1>天钧引擎</h1>
      </div>
      <section className="status-deck" aria-label="系统状态">
        <div className="status-chip">
          <span id="statusDot" />
          <span id="statusText">连接中</span>
        </div>
        <div className="status-chip">
          模型 <strong id="modelStatus">检查中</strong>
        </div>
        <div className="status-chip">
          Hermes <strong id="hermesLlmStatus">检查中</strong>
        </div>
        <div className="status-chip">
          同步 <strong id="lastSync">--:--:--</strong>
        </div>
        <button id="refreshButton" className="pill-button">刷新</button>
      </section>
    </header>
  );
}
