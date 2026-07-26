from __future__ import annotations


CONFIRM_WORDS = (
    "确认", "提交", "同意", "批准", "可以执行", "开始执行",
    "commit", "approve", "submit", "yes",
)
CANCEL_WORDS = ("取消", "先不", "不要提交", "别提交", "stop", "cancel")
FEEDBACK_WORDS = (
    "太高", "太慢", "太贵", "不满意", "优化", "调整", "换", "降低", "提高",
    "成本", "预算", "延迟", "时延", "安全", "sla", "qos", "反馈",
)
REGION_LABELS = {
    "east": "东部区域", "west": "西部区域", "south": "华南区域", "dc1": "DC1",
    "dc2": "DC2", "dc3": "DC3", "shanghai": "上海", "beijing": "北京",
    "hangzhou": "杭州", "shenzhen": "深圳", "guangzhou": "广州", "dongguan": "东莞",
    "chengdu": "成都", "chongqing": "重庆", "wuhan": "武汉", "huizhou": "惠州",
    "zhuhai": "珠海", "foshan": "佛山", "zhongshan": "中山",
}
WORKLOAD_LABELS = {
    "inference": "推理", "training": "训练", "streaming": "流式处理",
    "analytics": "分析", "batch": "批处理",
}
FACTOR_LABELS = {
    "network": "网络质量", "completion": "任务完成能力", "performance": "算力性能",
    "security": "安全匹配度", "cost": "成本表现", "load": "负载余量",
    "availability": "可用性",
}
