#!/usr/bin/env python3
"""游资识别模块"""

# 知名游资关键词映射
FAMOUS_TRADERS = {
    '章盟主': ['江苏路', '国泰海通上海'],
    '赵老哥': ['银河绍兴'],
    '孙哥': ['溧阳路'],
    '炒股养家': ['华鑫上海', '华鑫证券上海'],
    '方新侠': ['兴业陕西'],
    '小鳄鱼': ['大钟亭'],
    '作手新一': ['太平南路'],
    '宁波桑田路': ['桑田路'],
    '佛山系': ['佛山季华', '佛山绿景'],
    '上塘路': ['上塘路'],
}

def match_trader(seat_name):
    """识别游资外号"""
    for alias, keywords in FAMOUS_TRADERS.items():
        for kw in keywords:
            if kw in seat_name:
                return alias
    return None
