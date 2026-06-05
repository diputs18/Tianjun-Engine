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
    dc1: "数据中心 1",
    dc2: "数据中心 2",
    dc3: "数据中心 3",
    east: "华东",
    west: "西部",
    south: "华南",
    north: "华北",
    central: "华中",
    wuhan: "武汉",
    beijing: "北京",
    tianjin: "天津",
    shanghai: "上海",
    hangzhou: "杭州",
    nanjing: "南京",
    suzhou: "苏州",
    wuxi: "无锡",
    ningbo: "宁波",
    hefei: "合肥",
    jinan: "济南",
    qingdao: "青岛",
    chengdu: "成都",
    chongqing: "重庆",
    xian: "西安",
    kunming: "昆明",
    guiyang: "贵阳",
    lanzhou: "兰州",
    urumqi: "乌鲁木齐",
    guangzhou: "广州",
    shenzhen: "深圳",
    dongguan: "东莞",
    huizhou: "惠州",
    zhuhai: "珠海",
    foshan: "佛山",
    zhongshan: "中山",
    xiamen: "厦门",
    fuzhou: "福州",
    nanning: "南宁",
    haikou: "海口",
  };
  if (value == null || value === "") return "-";
  const normalized = String(value).trim().toLowerCase();
  return map[normalized] ?? String(value);
}

export function statusLabel(value) {
  const map = {
    online: "在线",
    offline: "离线",
    enabled: "已启用",
    disabled: "已停用",
    fallback: "回退模式",
    loaded: "已加载",
    loading: "加载中",
    unknown: "未知",
    ok: "正常",
    degraded: "降级",
    committed: "已提交",
    pending: "待处理",
    running: "运行中",
    succeeded: "成功",
    failed: "失败",
  };
  if (value == null || value === "") return "-";
  const normalized = String(value).trim().toLowerCase();
  return map[normalized] ?? String(value);
}
