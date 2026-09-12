"""Simple Travel Assistant 使用的本地模拟数据。

这些数据只用于教学演示，不代表真实天气、开放状态或票价。
"""

from __future__ import annotations


WEATHER_DATA: dict[str, dict[str, object]] = {
    "北京": {
        "condition": "晴",
        "temperature": 30,
        "humidity": 45,
        "wind": "微风",
    },
    "上海": {
        "condition": "多云",
        "temperature": 27,
        "humidity": 70,
        "wind": "东南风",
    },
    "广州": {
        "condition": "阵雨",
        "temperature": 32,
        "humidity": 82,
        "wind": "南风",
    },
}


ATTRACTION_DATA: dict[str, dict[str, object]] = {
    "故宫": {
        "city": "北京",
        "open": True,
        "adult_ticket": 60,
        "activity_type": "室内外步行",
        "description": (
            "以宫殿建筑、历史展陈和步行参观为主。"
        ),
    },
    "上海博物馆": {
        "city": "上海",
        "open": True,
        "adult_ticket": 0,
        "activity_type": "室内参观",
        "description": (
            "以历史文物和艺术展陈为主。"
        ),
    },
    "广东省博物馆": {
        "city": "广州",
        "open": False,
        "adult_ticket": 0,
        "activity_type": "室内参观",
        "description": (
            "当前模拟数据中处于闭馆状态。"
        ),
    },
}
