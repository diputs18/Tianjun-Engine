import ReactECharts from "echarts-for-react";
import { useThemeTokens } from "../../theme/useThemeTokens.js";

export function SlaChart({ slaRate = 0, successRate = 0 }) {
  const tokens = useThemeTokens();
  const sla = Number((slaRate * 100).toFixed(1));
  const success = Number((successRate * 100).toFixed(1));
  const option = {
    animation: false,
    grid: { left: 44, right: 28, top: 28, bottom: 34 },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: ["-24h", "-18h", "-12h", "-6h", "现在"],
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: tokens.textSecondary, fontSize: 13 },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      interval: 100,
      axisLabel: { formatter: "{value}%", color: tokens.textSecondary, fontSize: 13 },
      splitLine: { lineStyle: { type: "dashed", color: tokens.line } },
    },
    series: [
      {
        name: "SLA",
        type: "line",
        symbol: "none",
        data: [sla, sla, sla, sla, sla],
        lineStyle: { width: 3, color: tokens.blue },
      },
      {
        name: "执行成功率",
        type: "line",
        symbol: "none",
        data: [success, success, success, success, success],
        lineStyle: { width: 2, color: tokens.green },
      },
    ],
  };
  return <ReactECharts option={option} style={{ height: 176 }} />;
}
