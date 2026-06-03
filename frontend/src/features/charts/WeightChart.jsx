import ReactECharts from "echarts-for-react";

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
  const entries = Object.entries(weights);
  const option = {
    grid: { left: 96, right: 24, top: 18, bottom: 24 },
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
