import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.locator("#systemStatus")).toHaveText("系统在线");
});

test("tabs expose selection state and support keyboard navigation", async ({ page }) => {
  const overview = page.locator("#tab-overview");
  const scheduling = page.locator("#tab-scheduling");
  const topology = page.locator("#tab-topology");

  await expect(overview).toHaveAttribute("aria-selected", "true");
  await overview.focus();
  await page.keyboard.press("ArrowRight");
  await expect(scheduling).toBeFocused();
  await expect(scheduling).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#page-scheduling")).toBeVisible();
  await page.keyboard.press("End");
  await expect(page.locator("#tab-model")).toBeFocused();
  await page.keyboard.press("Home");
  await expect(overview).toBeFocused();
  await topology.click();
  await expect(topology).toHaveAttribute("aria-selected", "true");
  await expect(page).toHaveURL(/#topology$/);
});

test("latest navigation wins when an earlier polling response is delayed", async ({ page }) => {
  let delayed = false;
  await page.route("**/report/summary", async (route) => {
    if (!delayed) {
      delayed = true;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    await route.continue();
  });
  await page.reload();
  await page.locator("#tab-topology").click();
  await expect(page.locator("#page-topology")).toBeVisible();
  await page.waitForTimeout(350);
  await expect(page.locator("#tab-topology")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#page-topology")).toBeVisible();
});

test("topology layers change both semantics and visible supporting content", async ({ page }) => {
  await page.locator("#tab-topology").click();
  const canvas = page.locator("#topologyCanvas");
  const load = page.getByRole("button", { name: "资源负载" });
  const carbon = page.getByRole("button", { name: "碳强度" });

  await expect(canvas).toHaveAttribute("data-layer", "network");
  await load.click();
  await expect(load).toHaveAttribute("aria-pressed", "true");
  await expect(canvas).toHaveAttribute("data-layer", "load");
  await expect(page.locator("#pathMetrics")).toBeHidden();
  await expect(page.locator("#topologyLayerSummary")).toContainText("数据中心负载");
  await carbon.click();
  await expect(carbon).toHaveAttribute("aria-pressed", "true");
  await expect(canvas).toHaveAttribute("data-layer", "carbon");
  await expect(page.locator("#topologyLayerSummary")).toContainText("站点碳强度");
});

test("empty topology and failed health requests have explicit states", async ({ page }) => {
  await page.route("**/report/topology", async (route) => {
    const response = await route.fetch();
    const report = await response.json();
    await route.fulfill({ response, json: { ...report, nodes: [], physical_topology: null } });
  });
  await page.locator("#tab-topology").click();
  await expect(page.locator(".topology-empty-state")).toBeVisible();
  await expect(page.locator(".topology-empty-state")).toContainText("等待仿真节点导入");

  await page.route("**/health", (route) => route.abort("failed"));
  await page.locator("#refreshButton").click();
  await expect(page.locator("#systemStatus")).toHaveText("系统离线");
  await expect(page.locator("#autoRefreshStatus")).toContainText("刷新失败");
});

test("topology geometry stays inside its canvas without page overflow", async ({ page }) => {
  await page.locator("#tab-topology").click();
  await expect(page.locator(".network-topology-shell")).toBeVisible();
  const geometry = await page.evaluate(() => {
    const canvas = document.querySelector("#topologyCanvas").getBoundingClientRect();
    const shell = document.querySelector(".network-topology-shell").getBoundingClientRect();
    const svg = document.querySelector(".network-links")?.getBoundingClientRect();
    const nodes = Array.from(document.querySelectorAll(".network-node")).map((node) => {
      const rect = node.getBoundingClientRect();
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
    });
    return {
      viewportWidth: document.documentElement.clientWidth,
      documentWidth: document.documentElement.scrollWidth,
      canvas: {
        left: canvas.left,
        right: canvas.right,
        top: canvas.top,
        bottom: canvas.bottom,
      },
      shell: { left: shell.left, right: shell.right, top: shell.top, bottom: shell.bottom },
      svg: svg && { left: svg.left, right: svg.right, top: svg.top, bottom: svg.bottom },
      nodes,
    };
  });
  expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.shell.left).toBeGreaterThanOrEqual(geometry.canvas.left - 1);
  expect(geometry.shell.right).toBeLessThanOrEqual(geometry.canvas.right + 1);
  if (geometry.svg) {
    expect(geometry.svg.left).toBeGreaterThanOrEqual(geometry.shell.left - 1);
    expect(geometry.svg.right).toBeLessThanOrEqual(geometry.shell.right + 1);
  }
  for (const node of geometry.nodes) {
    expect(node.left).toBeGreaterThanOrEqual(geometry.shell.left - 1);
    expect(node.right).toBeLessThanOrEqual(geometry.shell.right + 1);
    expect(node.top).toBeGreaterThanOrEqual(geometry.shell.top - 1);
    expect(node.bottom).toBeLessThanOrEqual(geometry.shell.bottom + 1);
  }
});
