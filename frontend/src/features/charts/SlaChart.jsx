import ReactECharts from "echarts-for-react";

export function SlaChart({ slaRate = 0, successRate = 0 }) {
  const option = {
    tooltip: { trigger: "item" },
    legend: { bottom: 0, textStyle: { color: "#667085" } },
    series: [
      {
        name: "SLA",
        type: "pie",
        radius: ["58%", "76%"],
        center: ["32%", "45%"],
        label: { formatter: "{b}\n{d}%" },
        data: [
          { value: slaRate, name: "达标", itemStyle: { color: "#176b87" } },
          { value: Math.max(0, 1 - slaRate), name: "未达标", itemStyle: { color: "#e6edf1" } },
        ],
      },
      {
        name: "成功率",
        type: "pie",
        radius: ["44%", "55%"],
        center: ["72%", "45%"],
        label: { formatter: "{b}\n{d}%" },
        data: [
          { value: successRate, name: "成功", itemStyle: { color: "#2a9d8f" } },
          { value: Math.max(0, 1 - successRate), name: "失败/等待", itemStyle: { color: "#e9ecef" } },
        ],
      },
    ],
  };
  return <ReactECharts option={option} style={{ height: 280 }} />;
}
