"""
用 DeepSeek API 分析 Google Play 评论情绪，返回结构化数据。
使用 function calling 确保 JSON 输出稳定。
"""
import json
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL

_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

_SYSTEM = """你是一名资深手游市场分析专家，专注于 Google Play 玩家评论分析。
根据提供的评论数据（含星级评分），调用 report_sentiment 函数返回结构化中文分析报告。

分析要求：
- 情绪百分比之和必须为 100，需结合星级分布判断（1-2星=负面，3星=中立，4-5星=正面）
- 代表评论需包含原文摘要、星级和点赞数
- 异常/突发事件：若无则填「暂无」
- 所有输出文字使用中文"""

_TOOL = {
    "type": "function",
    "function": {
        "name": "report_sentiment",
        "description": "输出 Google Play 评论情绪分析报告的结构化数据",
        "parameters": {
            "type": "object",
            "properties": {
                "positive_pct":         {"type": "integer", "description": "积极情绪占比 (0-100)"},
                "negative_pct":         {"type": "integer", "description": "消极情绪占比 (0-100)"},
                "neutral_pct":          {"type": "integer", "description": "中立情绪占比 (0-100)"},
                "avg_stars":            {"type": "number",  "description": "今日评论平均星级（保留1位小数）"},
                "sentiment_explanation":{"type": "string",  "description": "整体情绪概述（2-3句话）"},
                "top_positive_reviews": {"type": "string",  "description": "前3条高影响力正面评论摘要（含原文要点、星级、点赞数）"},
                "top_negative_reviews": {"type": "string",  "description": "前3条高影响力负面评论摘要（含原文要点、星级、点赞数）"},
                "hot_topics":           {"type": "string",  "description": "玩家最集中反映的问题或话题"},
                "emergent_events":      {"type": "string",  "description": "突发事件或新兴关注点，无则写「暂无」"},
                "anomalies":            {"type": "string",  "description": "异常情况，无则写「暂无」"},
            },
            "required": [
                "positive_pct", "negative_pct", "neutral_pct", "avg_stars",
                "sentiment_explanation", "top_positive_reviews", "top_negative_reviews",
                "hot_topics", "emergent_events", "anomalies",
            ],
        },
    },
}


def analyze_sentiment(reviews_summary: str, group_name: str) -> dict:
    response = _client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    f"以下是今日「{group_name}」Google Play 评论数据（已按影响力排序），请分析玩家情绪：\n\n"
                    f"{reviews_summary}"
                ),
            },
        ],
        tools=[_TOOL],
        tool_choice={"type": "function", "function": {"name": "report_sentiment"}},
    )
    tool_call = response.choices[0].message.tool_calls[0]
    return json.loads(tool_call.function.arguments)
