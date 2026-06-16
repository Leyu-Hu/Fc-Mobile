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

_SYSTEM_ZH = """你是一名资深社交媒体分析专家，专注于海外游戏社区舆情分析（Reddit 平台）。
根据提供的 Reddit 帖子数据，调用 report_sentiment 函数返回结构化的中文分析报告。

分析要求：
- 情绪百分比之和必须为 100
- 代表帖子需包含标题摘要和互动数据
- 异常/突发事件：若无则填「暂无」
- 单独提炼「Gameplay / 赛中体验」相关讨论（操作手感、匹配、延迟、AI/防守、技能动作、平衡、判定、PvP 对战体验、赛中 bug 等），填入 gameplay_summary，与卡池/经济/活动话题区分开
- 所有输出文字使用中文"""

_SYSTEM_EN = """You are a senior social media analyst specialising in gaming community sentiment analysis on Reddit.
Based on the provided Reddit post data, call the report_sentiment function to return a structured English analysis report.

Requirements:
- Sentiment percentages must sum to 100
- Representative posts must include title summary and engagement data
- Anomalies/emerging events: write "None" if not applicable
- Separately summarise "Gameplay / in-match experience" discussions (controls/feel, matchmaking, lag, AI & defending, skills & animations, balance, refereeing/goals, PvP/VSA match feel, in-match bugs) into gameplay_summary, distinct from card-pool/economy/event topics
- IMPORTANT: Every single field must be written in English — do NOT use any Chinese characters"""

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
                "gameplay_summary":   {"type": "string", "description": "专门针对【Gameplay / 赛中体验】相关讨论的摘要：聚焦操作手感、对战匹配、延迟/卡顿、AI 与防守表现、技能与动作、平衡性、进球/判定、PvP/VSA 对战体验、赛中 bug 等；明确排除卡池/抽卡/经济/活动/养成等非赛中话题。提炼 3-5 条玩家在赛中体验上的主要反馈（标明正面/负面倾向，尽量带帖子标题或互动数），若无相关讨论则写「暂无」"},
            },
            "required": [
                "positive_pct", "negative_pct", "neutral_pct",
                "sentiment_explanation", "top_positive_posts", "top_negative_posts",
                "hot_topics", "emergent_events", "anomalies", "gameplay_summary",
            ],
        },
    },
}


def analyze_sentiment(posts_summary: str, subreddits: list[str], lang: str = "zh") -> dict:
    sub_names = " + ".join(f"r/{s}" for s in subreddits)
    if lang == "en":
        system = _SYSTEM_EN
        user_prompt = (
            f"Here is today's post data from {sub_names} (sorted by impact score), "
            f"please analyse the community sentiment:\n\n{posts_summary}"
        )
    else:
        system = _SYSTEM_ZH
        user_prompt = (
            f"以下是今日 {sub_names} 的帖子数据（已按影响力排序），请分析社区情绪：\n\n"
            f"{posts_summary}"
        )
    response = _client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        tools=[_TOOL],
        tool_choice={"type": "function", "function": {"name": "report_sentiment"}},
        max_tokens=4096,
    )

    tool_call = response.choices[0].message.tool_calls[0]
    raw = tool_call.function.arguments
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 截断时尝试补全 JSON
        fixed = raw.rstrip(", \t\n\r") + '"}}'
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            # 返回降级结果，避免整个分组失败
            print(f"  [WARN] DeepSeek 返回 JSON 解析失败，使用降级结果。原始：{raw[:200]}")
            return {
                "positive_pct": 0, "negative_pct": 0, "neutral_pct": 100,
                "sentiment_explanation": "（分析失败，请重试）",
                "top_positive_posts": "N/A", "top_negative_posts": "N/A",
                "hot_topics": "N/A", "emergent_events": "N/A", "anomalies": "N/A",
                "gameplay_summary": "N/A",
            }
