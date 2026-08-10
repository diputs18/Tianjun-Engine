import assert from "node:assert/strict";
import test from "node:test";

import {
  carbonSourceSummary,
  loadSourceSummary,
  sourceLabel,
} from "../../src/tianjun/interfaces/dashboard/static/js/topology-data.js";
import {
  aggregateResources,
  parseDciNode,
  vmDisplayName,
} from "../../src/tianjun/interfaces/dashboard/static/js/topology-resource.js";

test("resource layer distinguishes real, simulated, estimated and mixed data", () => {
  assert.equal(loadSourceSummary([{ resource_load_source: "live_telemetry" }]), "实时遥测");
  assert.equal(loadSourceSummary([{ resource_load_source: "simulated_telemetry" }]), "CloudSim 模拟");
  assert.equal(loadSourceSummary([{ resource_load_source: "allocation_estimate" }]), "分配估算");
  assert.equal(loadSourceSummary([
    { resource_load_source: "live_telemetry" },
    { resource_load_source: "allocation_estimate" },
  ]), "混合来源");
  assert.equal(loadSourceSummary([{ resource_load_source: "unavailable" }]), "暂无数据");
});

test("carbon layer never labels a configured profile as realtime", () => {
  assert.equal(carbonSourceSummary([{ carbon_data_source: "configured_profile" }]), "配置曲线");
  assert.equal(carbonSourceSummary([{ carbon_data_source: "simulated_profile" }]), "模拟曲线");
  assert.equal(sourceLabel(["live_signal"], "carbon"), "实时碳信号");
});

test("topology resource aggregation prefers heartbeat telemetry over allocation estimates", () => {
  const parsed = parseDciNode("dci-dc2-chengdu-vm-3");
  assert.deepEqual(parsed, { dcKey: "dc2", location: "chengdu", vmIndex: 3 });
  const result = aggregateResources([{
    node_id: "dci-dc2-chengdu-vm-3",
    capacity: { cpu: 8, memory: 16, gpu: 2 },
    available: { cpu: 7, memory: 14, gpu: 2 },
    runtime_utilization: { cpu: 0.5, memory: 0.25 },
    active_task_ids: ["task-a"],
  }], "dc").get("dc2");
  assert.equal(result.cpuPercent, 50);
  assert.equal(result.memoryPercent, 25);
  assert.equal(result.tasks, 1);
});

test("topology VM labels preserve the backend numeric suffix", () => {
  assert.equal(vmDisplayName(parseDciNode("dci-dc1-hangzhou-vm-1").vmIndex), "VM-01");
  assert.equal(vmDisplayName(parseDciNode("dci-dc2-chongqing-vm-0").vmIndex), "VM-00");
});
