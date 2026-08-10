import assert from "node:assert/strict";
import test from "node:test";

import { resourceValue } from "../../src/tianjun/interfaces/dashboard/static/js/pages/overview.js";

test("overview resource pool shows scheduler allocation instead of stale host telemetry", () => {
  const idleNode = {
    capacity: { cpu: 8, memory: 16 },
    available: { cpu: 8, memory: 16 },
    runtime_utilization: { cpu: 0.17, memory: 0.16 },
  };
  assert.equal(resourceValue(idleNode, "cpu"), 0);
  assert.equal(resourceValue(idleNode, "memory"), 0);

  const allocatedNode = {
    capacity: { cpu: 8, memory: 16 },
    available: { cpu: 6, memory: 12 },
    runtime_utilization: { cpu: 0.9, memory: 0.8 },
  };
  assert.equal(resourceValue(allocatedNode, "cpu"), 0.25);
  assert.equal(resourceValue(allocatedNode, "memory"), 0.25);
});

test("overview falls back to telemetry when allocation capacity is unavailable", () => {
  const telemetryOnlyNode = {
    runtime_utilization: { cpu: 0.42, memory: 0.31 },
  };
  assert.equal(resourceValue(telemetryOnlyNode, "cpu"), 0.42);
  assert.equal(resourceValue(telemetryOnlyNode, "memory"), 0.31);
});
