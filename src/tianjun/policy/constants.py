from __future__ import annotations


REGION_ALIASES = {
    "东部区域": "east", "东部": "east", "华东": "east", "华北": "east",
    "上海": "east", "杭州": "east", "北京": "east", "天津": "east",
    "南京": "east", "苏州": "east", "无锡": "east", "宁波": "east",
    "合肥": "east", "济南": "east", "青岛": "east",
    "西部区域": "west", "西部": "west", "西南": "west", "成都": "west",
    "重庆": "west", "西安": "west", "昆明": "west", "贵阳": "west",
    "兰州": "west", "乌鲁木齐": "west",
    "华南区域": "south", "华南": "south", "深圳": "south", "广州": "south",
    "东莞": "south", "惠州": "south", "珠海": "south", "佛山": "south",
    "中山": "south", "厦门": "south", "福州": "south", "南宁": "south",
    "海口": "south", "武汉": "wuhan", "华中": "wuhan",
    "east": "east", "east china": "east", "shanghai": "east",
    "hangzhou": "east", "beijing": "east", "tianjin": "east",
    "nanjing": "east", "suzhou": "east", "west": "west",
    "chengdu": "west", "chongqing": "west", "cd": "west", "cq": "west",
    "south": "south", "south china": "south", "shenzhen": "south",
    "guangzhou": "south", "dongguan": "south", "huizhou": "south",
    "zhuhai": "south", "foshan": "south", "zhongshan": "south",
    "wuhan": "wuhan",
}

SERVICE_REGION_CODES = {"east", "west", "south", "wuhan"}
GUANGDONG_REGIONS = ["south"]
PRIORITY_VECTOR_KEYS = {
    "latency", "cost", "quality", "security", "balance", "fragmentation",
    "locality", "network", "carbon",
}
PRIORITY_TO_METRICS = {
    "latency": {"performance": 0.52, "completion": 0.18, "network": 0.30},
    "cost": {"cost": 1.0},
    "quality": {"reliability": 0.58, "completion": 0.24, "performance": 0.18},
    "security": {"security": 0.76, "reliability": 0.14, "locality": 0.10},
    "balance": {"balance": 1.0},
    "fragmentation": {"fragmentation": 1.0},
    "locality": {"locality": 1.0},
    "network": {"network": 0.78, "performance": 0.22},
    "carbon": {"carbon": 0.82, "cost": 0.08, "fragmentation": 0.10},
}
