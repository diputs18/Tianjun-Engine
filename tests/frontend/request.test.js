import assert from "node:assert/strict";
import test from "node:test";

import {
  RequestTimeoutError,
  requestJson,
} from "../../src/tianjun/interfaces/dashboard/static/js/request.js";

test("requestJson executes the real response parsing path", async () => {
  const payload = await requestJson("/health", {
    fetchImpl: async (path, options) => {
      assert.equal(path, "/health");
      assert.equal(options.method, "GET");
      return new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    },
  });
  assert.deepEqual(payload, { status: "ok" });
});

test("requestJson aborts a hung fetch at its deadline", async () => {
  const hungFetch = (_path, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener("abort", () => reject(options.signal.reason), { once: true });
  });
  await assert.rejects(
    requestJson("/report/summary", { fetchImpl: hungFetch, timeoutMs: 100 }),
    (error) => error instanceof RequestTimeoutError,
  );
});
