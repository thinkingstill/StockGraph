def min_max_normalize(column):
    if len(column) == 0:
        return column
    minimum = column.min()
    maximum = column.max()
    if minimum is None or maximum is None or maximum == minimum:
        if hasattr(column, "map"):
            return column.map(lambda _: 100.0)
        return [100.0 for _ in column]
    normalized = ((column - minimum) / (maximum - minimum)) * 100
    return normalized.round(1) if hasattr(normalized, "round") else [round(value, 1) for value in normalized]


def get_exchange(code: str) -> str:
    if code.startswith("688"):
        return "上海证券交易所科创板"
    if code.startswith("920") or code.startswith("8"):
        return "北京证券交易所"
    if code.startswith("689"):
        return "上海证券交易所科创板（CDR公司）"
    if code.startswith(("600", "601", "603", "605")):
        return "上海证券交易所主板"
    if code.startswith("000"):
        return "深圳证券交易所主板"
    if code.startswith(("001", "002")):
        return "深圳证券交易所中小板"
    if code.startswith(("003", "300", "301")):
        return "深圳证券交易所创业板"
    if code.startswith("430"):
        return "新三板"
    return "无法识别的股票代码"
