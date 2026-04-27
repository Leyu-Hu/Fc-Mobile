"""
对应原步骤 4：用 DeepSeek API 分析社区帖子情绪，返回结构化数据。
DeepSeek 兼容 OpenAI 接口，使用 function calling 确保 JSON 输出稳定。
"""
import json
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL

_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)

_SYSTEM = """你是一名资深社交媒体分析专家，专注于海外游戏社区舆情分析（Reddit 平台）。
根据提供的 Reddit 帖子数据，调用 report_sentiment 函数返回结构化的中文分析报告。

分析要求：
- 情绪百分比之和必须为 100
- 代表帖子需包含标题摘要和互动数据
- 异常/突发事件：若无则填「暂无」
- 所有输出文字使用中文"""

_TOOL = {
    "type": "function",
    "function": {
        "name": "report_sentiment",
        "description": "输出社区帖子情绪分析报告的结构化数据",
        "parameters": {
            "type": "object",
            "properties": {
                "positive_pct": {"type": "integer", "description": "积极情绪占比 (0-100)"},
                "negative_pct": {"type": "integer", "description": "消极情绪占比 (0-100)"},
                "neutral_pct":  {"type": "integer", "description": "中立情绪占比 (0-100)"},
                "sentiment_explanation": {"type": "string", "description": "整体情绪概述（2-3句话，说明趋势和可能原因）"},
                "top_positive_posts": {"type": "string", "description": "前3条高影响力正面帖子摘要（含标题、互动数、URL）"},
                "top_negative_posts": {"type": "string", "description": "前3条高影响力负面帖子摘要（含标题、互动数、URL）"},
                "hot_topics":         {"type": "string", "description": "最热门讨论话题分析（含话题名称和参与数据）"},
                "emergent_events":    {"type": "string", "description": "突发事件或新兴关注点，无则写「暂无」"},
                "anomalies":          {"type": "string", "description": "显著偏离正常模式的异常情况，无则写「暂无」"},
            },
            "required": [
                "positive_pct", "negative_pct", "neutral_pct",
                "sentiment_explanation", "top_positive_posts", "top_negative_posts",
                "hot_topics", "emergent_events", "anomalies",
            ],
        },
    },
}


def analyze_sentiment(posts_summary: str, subreddits: list[str]) -> dict:
    """
    输入：格式化的帖子摘要文本
    返回：结构化情绪分析 dict
    """
    sub_names = " + ".join(f"r/{s}" for s in subreddits)
    response = _client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    f"以下是今日 {sub_names} 的帖子数据（已按影响力排序），请分析社区情绪：\n\n"
                    f"{posts_summary}"
                ),
            },
        ],
        tools=[_TOOL],
        tool_choice={"type": "function", "function": {"name": "report_sentiment"}},
    )

    tool_call = response.choices[0].message.tool_calls[0]
    return json.loads(tool_call.function.arguments)
