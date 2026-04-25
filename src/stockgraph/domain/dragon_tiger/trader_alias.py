SEAT_TYPE_KEYWORDS = {
    "机构": ["机构专用", "机构席位", "专用席位", "社保", "基金", "保险", "券商自营"],
    "外资": ["沪股通", "深股通", "沪港通", "深港通", "港股通", "外资", "QFII", "RQFII"],
    "游资": ["营业部", "分公司", "证券", "投资", "资本", "财富", "咨询"],
}

FAMOUS_TRADERS = {
    "章盟主": ["江苏路", "国泰海通上海"],
    "赵老哥": ["银河绍兴"],
    "孙哥": ["溧阳路"],
    "炒股养家": ["华鑫上海", "华鑫证券上海"],
    "方新侠": ["兴业陕西"],
    "小鳄鱼": ["大钟亭"],
    "作手新一": ["太平南路"],
    "宁波桑田路": ["桑田路"],
    "佛山系": ["佛山季华", "佛山绿景"],
    "上塘路": ["上塘路"],
}


def match_trader(seat_name: str) -> str | None:
    for alias, keywords in FAMOUS_TRADERS.items():
        if any(keyword in seat_name for keyword in keywords):
            return alias
    return None


def detect_seat_type(seat_name: str) -> str:
    normalized = seat_name.lower()
    for keyword in SEAT_TYPE_KEYWORDS["机构"]:
        if keyword.lower() in normalized:
            return "机构"
    for keyword in SEAT_TYPE_KEYWORDS["外资"]:
        if keyword.lower() in normalized:
            return "外资"
    return "游资"
