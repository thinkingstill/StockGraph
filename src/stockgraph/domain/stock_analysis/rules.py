"""基于日线、新闻和龙虎榜的轻量可解释研判。

这些规则只用于整理证据和风险，不构成投资建议。刻意不使用黑盒预测，
以便前端能把每一项得分和触发条件展示给用户。
"""

from __future__ import annotations

from statistics import mean


def _number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _ma(values: list[float], window: int) -> float | None:
    return round(mean(values[-window:]), 3) if len(values) >= window else None


def _rsi(closes: list[float], window: int = 14) -> float | None:
    if len(closes) <= window:
        return None
    changes = [closes[i] - closes[i - 1] for i in range(-window, 0)]
    gains = sum(change for change in changes if change > 0) / window
    losses = -sum(change for change in changes if change < 0) / window
    if losses == 0:
        return 100.0
    return round(100 - 100 / (1 + gains / losses), 2)


def analyze_price_history(
    rows: list[dict], *, news: list[dict] | None = None, dragon_tiger: list[dict] | None = None
) -> dict:
    """返回趋势、动量、量能、风险和评分；输入按日期升序的日线。"""
    normalized = [row for row in rows if _number(row.get("close")) > 0]
    closes = [_number(row["close"]) for row in normalized]
    volumes = [_number(row.get("volume")) for row in normalized]
    if len(closes) < 5:
        return {"available": False, "message": "至少需要 5 个交易日的日线数据才能研判。"}

    latest = closes[-1]
    ma5, ma10, ma20, ma60 = (_ma(closes, n) for n in (5, 10, 20, 60))
    return_5 = round((latest / closes[-6] - 1) * 100, 2) if len(closes) >= 6 else None
    return_20 = round((latest / closes[-21] - 1) * 100, 2) if len(closes) >= 21 else None
    rsi14 = _rsi(closes)
    volume_ratio = round(_ma(volumes, 5) / _ma(volumes, 20), 2) if _ma(volumes, 5) and _ma(volumes, 20) else None

    score = 50
    evidence: list[dict] = []
    risks: list[str] = []
    if ma20 is not None:
        if latest > ma20:
            score += 12
            evidence.append({"dimension": "趋势", "signal": "价格位于 MA20 上方", "impact": "+12"})
        else:
            score -= 12
            evidence.append({"dimension": "趋势", "signal": "价格位于 MA20 下方", "impact": "-12"})
    if ma5 is not None and ma10 is not None:
        if ma5 > ma10:
            score += 8
            evidence.append({"dimension": "趋势", "signal": "MA5 高于 MA10", "impact": "+8"})
        else:
            score -= 8
            evidence.append({"dimension": "趋势", "signal": "MA5 低于 MA10", "impact": "-8"})
    if return_20 is not None:
        delta = 8 if return_20 >= 0 else -8
        score += delta
        evidence.append({"dimension": "动量", "signal": f"20 日涨跌幅 {return_20:+.2f}%", "impact": f"{delta:+d}"})
    if volume_ratio is not None:
        if volume_ratio >= 1.2 and (return_5 or 0) > 0:
            score += 6
            evidence.append({"dimension": "量能", "signal": f"5/20 日量比 {volume_ratio}", "impact": "+6"})
        elif volume_ratio >= 1.8 and (return_5 or 0) < 0:
            score -= 6
            evidence.append({"dimension": "量能", "signal": f"下跌放量，量比 {volume_ratio}", "impact": "-6"})
            risks.append("下跌放量，需警惕抛压延续")
    if rsi14 is not None:
        if rsi14 > 75:
            score -= 5
            risks.append(f"RSI(14)={rsi14}，短线可能过热")
        elif rsi14 < 25:
            score += 3
            risks.append(f"RSI(14)={rsi14}，超卖不等于见底，仍需等待确认")

    sentiment = {"利好": 0, "利空": 0}
    for item in news or []:
        if item.get("sentiment") in sentiment:
            sentiment[item["sentiment"]] += 1
    news_delta = min(8, (sentiment["利好"] - sentiment["利空"]) * 2)
    score += news_delta
    if sentiment["利好"] or sentiment["利空"]:
        evidence.append({"dimension": "消息", "signal": f"利好 {sentiment['利好']} 条 / 利空 {sentiment['利空']} 条", "impact": f"{news_delta:+d}"})

    net_flow = 0.0
    for day in dragon_tiger or []:
        for op in day.get("operations", []):
            amount = _number(op.get("amount"))
            net_flow += amount if op.get("direction") in {"买", "买入"} else -amount
    if net_flow:
        delta = 6 if net_flow > 0 else -6
        score += delta
        evidence.append({"dimension": "资金", "signal": f"龙虎榜样本净额 {net_flow:,.0f}", "impact": f"{delta:+d}"})

    score = max(0, min(100, round(score)))
    level = "偏强" if score >= 65 else "偏弱" if score < 40 else "中性"
    if ma60 is not None and latest < ma60:
        risks.append("价格仍低于 MA60，中期趋势尚未完全修复")
    return {
        "available": True,
        "method": "趋势(MA) + 动量(5/20日收益) + RSI + 量能 + 新闻情绪 + 龙虎榜资金",
        "score": score,
        "level": level,
        "metrics": {"close": latest, "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60, "return_5": return_5, "return_20": return_20, "rsi14": rsi14, "volume_ratio": volume_ratio},
        "evidence": evidence,
        "risks": risks,
        "disclaimer": "规则研判仅作研究辅助，不构成买卖建议；历史表现不代表未来结果。",
    }
