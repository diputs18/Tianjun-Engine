import ReactECharts from "echarts-for-react";

const labels = {
  performance: "性能",
  completion: "完成率",
  cost: "成本",
  reliability: "可靠性",
  balance: "负载均衡",
  fragmentation: "碎片",
  locality: "局部性",
  network: "网络",
};

export function WeightChart({ weights = {} }) {
  const entries = Object.entries(weights);
  const option = {
    grid: { left: 72, right: 24, top: 18, bottom: 24 },
    xAxis: {
      type: "value",
      axisLabel: { color: "#667085" },
      splitLine: { lineStyle: { color: "rgba(16, 24, 40, 0.08)" } },
    },
    yAxis: {
      type: "category",
      data: entries.map(([key]) => labels[key] ?? key),
      axisLabel: { color: "#344054" },
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
          color: "#176b87",
        },
      },
    ],
    tooltip: {
      formatter: (params) => `${params.name}: ${(params.value * 100).toFixed(1)}%`,
    },
  };
  return <ReactECharts option={option} style={{ height: 300 }} />;
}
