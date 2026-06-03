import dayjs from "dayjs";

export function pct(value, digits = 1) {
  return `${(Number(value ?? 0) * 100).toFixed(digits)}%`;
}

export function num(value, digits = 2) {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed.toFixed(digits) : "-";
}

export function shortTime(value) {
  return value ? dayjs(value).format("HH:mm:ss") : "--:--:--";
}

export function regionLabel(value) {
  const map = {
    dc1: "DC1",
    dc2: "DC2",
    dc3: "DC3",
    east: "华东",
    west: "西南",
    south: "华南",
    beijing: "北京",
    hangzhou: "杭州",
    chengdu: "成都",
    chongqing: "重庆",
    guangzhou: "广州",
    shenzhen: "深圳",
  };
  return map[value] ?? value ?? "-";
}
