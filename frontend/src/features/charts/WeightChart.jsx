import ReactECharts from "echarts-for-react";
import { useThemeTokens } from "../../theme/useThemeTokens.js";

const labels = {
  performance: "Performance",
  completion: "Completion",
  cost: "Cost",
  reliability: "Reliability",
  balance: "Balance",
  fragmentation: "Fragmentation",
  locality: "Locality",
  network: "Network",
  security: "Security",
};

export function WeightChart({ weights = {} }) {
  const tokens = useThemeTokens();
  const entries = Object.entries(weights);
  const option = {
    grid: { left: 96, right: 24, top: 18, bottom: 24 },
    xAxis: {
      type: "value",
      axisLabel: { color: tokens.textMuted },
      splitLine: { lineStyle: { color: tokens.line } },
    },
    yAxis: {
      type: "category",
      data: entries.map(([key]) => labels[key] ?? key),
      axisLabel: { color: tokens.text },
      axisTick: { show: false },
      axisLine: { show: false },
    },
    series: [
      {
        type: "bar",
        data: entries.map(([, value]) => Number(value ?? 0)),
        barWidth: 12,
        itemStyle: {
          borderRadius: [0, 8, 8, 0],
          color: tokens.blue,
        },
      },
    ],
    tooltip: {
      formatter: (params) => `${params.name}: ${(params.value * 100).toFixed(1)}%`,
    },
  };
  return <ReactECharts option={option} style={{ height: 300 }} />;
}
