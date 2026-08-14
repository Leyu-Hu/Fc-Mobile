"""
对应原步骤 4：用 DeepSeek API 分析社区帖子情绪，返回结构化数据。
DeepSeek 兼容 OpenAI 接口。

解析策略（三级，避免整份报告退化成 N/A）：
  1. function calling 拿 arguments → json.loads
  2. 失败则 _salvage()：DeepSeek 常吐出「key 有引号、字符串 value 没引号」的伪 JSON，
     按已知字段名切片抢救出来（内容是完整的，只是不合法 JSON）
  3. 仍失败则换 response_format=json_object 重试一次
  4. 都失败才返回 N/A 降级结果
"""
import json
import re
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

# json_object 重试模式下追加的 schema 说明（function calling 的 schema 此时不生效）
_JSON_HINT_ZH = """
只输出一个 JSON 对象，不要有任何额外文字或 markdown 代码块。字段：
{"positive_pct": 整数, "negative_pct": 整数, "neutral_pct": 整数,
 "sentiment_explanation": "整体情绪概述，2-3 句",
 "top_positive_posts": "前3条高影响力正面帖子摘要，含标题、互动数、URL",
 "top_negative_posts": "前3条高影响力负面帖子摘要，含标题、互动数、URL",
 "hot_topics": "最热门讨论话题分析，含话题名称和参与数据",
 "emergent_events": "突发事件或新兴关注点，无则写「暂无」",
 "anomalies": "显著偏离正常模式的异常情况，无则写「暂无」",
 "gameplay_summary": "赛中体验讨论摘要，3-5 条，标明正面/负面倾向"}
所有字符串值必须用英文双引号包裹，内部换行写成 \\n，内部双引号必须转义。
内容要详实，不要为了简短而省略帖子标题和互动数据。"""

_JSON_HINT_EN = """
Output a single JSON object only — no extra prose, no markdown code fence. Fields:
{"positive_pct": int, "negative_pct": int, "neutral_pct": int,
 "sentiment_explanation": "2-3 sentence overall sentiment summary",
 "top_positive_posts": "Top 3 high-impact positive posts with title, engagement, URL",
 "top_negative_posts": "Top 3 high-impact negative posts with title, engagement, URL",
 "hot_topics": "Hottest discussion topics with names and engagement data",
 "emergent_events": "Emerging events or breaking concerns, 'None' if not applicable",
 "anomalies": "Notable deviations from normal patterns, 'None' if not applicable",
 "gameplay_summary": "3-5 in-match experience takeaways, each tagged positive/negative"}
Every string value must be wrapped in double quotes, inner newlines written as \\n, inner quotes escaped.
Be detailed — do not omit post titles or engagement numbers for the sake of brevity."""

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

# 字段顺序即 schema 顺序，_salvage 依此切片
_FIELDS = [
    "positive_pct", "negative_pct", "neutral_pct",
    "sentiment_explanation", "top_positive_posts", "top_negative_posts",
    "hot_topics", "emergent_events", "anomalies", "gameplay_summary",
]
_PCT_FIELDS = {"positive_pct", "negative_pct", "neutral_pct"}

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/"}


def _unescape(s: str) -> str:
    return re.sub(r'\\(["\\/ntr])', lambda m: _ESCAPES[m.group(1)], s)


def _salvage(raw: str) -> dict | None:
    """
    抢救 DeepSeek 吐出的伪 JSON：key 带引号但字符串 value 不带引号。
    按已知字段名定位，切出两个 key 之间的原始文本当作 value。
    """
    marks = []
    pos = 0
    for field in _FIELDS:
        m = re.compile(r'"%s"\s*:\s*' % re.escape(field)).search(raw, pos)
        if not m:
            return None          # 缺字段说明不是这种畸形，交给下一级
        marks.append((m.start(), m.end(), field))
        pos = m.end()

    out = {}
    for i, (_start, val_start, field) in enumerate(marks):
        val_end = marks[i + 1][0] if i + 1 < len(marks) else len(raw)
        val = raw[val_start:val_end].strip()
        val = re.sub(r'[\s,]+$', "", val)
        if i == len(marks) - 1 and val.endswith("}"):
            val = re.sub(r'[\s,]+$', "", val[:-1])

        if field in _PCT_FIELDS:
            num = re.search(r'-?\d+', val)
            out[field] = int(num.group()) if num else 0
            continue

        if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
            try:
                out[field] = json.loads(val)
                continue
            except json.JSONDecodeError:
                val = val[1:-1]
        # 裸文本里模型有时写成 \\n（多重反斜杠），先压成单反斜杠再反转义
        val = re.sub(r'\\{2,}(?=[ntr"])', "\\\\", val)
        out[field] = _unescape(val).strip()

    return out


def _parse(raw: str | None) -> dict | None:
    if not raw:
        return None
    raw = raw.strip()
    # json_object 模式偶尔会包 markdown 代码块
    if raw.startswith("```"):
        raw = re.sub(r'^```[a-zA-Z]*\s*', "", raw)
        raw = re.sub(r'\s*```$', "", raw)
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and all(f in data for f in _FIELDS):
            return data
    except json.JSONDecodeError:
        pass
    data = _salvage(raw)
    if data:
        print("  [INFO] DeepSeek 输出非合法 JSON，已按字段切片抢救成功。")
    return data


def _normalise(data: dict, lang: str) -> dict:
    blank = "None" if lang == "en" else "暂无"
    out = {}
    for field in _FIELDS:
        val = data.get(field)
        if field in _PCT_FIELDS:
            try:
                out[field] = int(float(val))
            except (TypeError, ValueError):
                out[field] = 0
        else:
            if val in (None, ""):
                out[field] = blank
            else:
                # 模型常在 JSON 字符串里写成 \\n，解码后是字面量反斜杠+n，还原成真换行
                out[field] = re.sub(r'\\+n', "\n", str(val)).strip()
    return out


def _fallback(lang: str) -> dict:
    msg = "(Analysis failed, please retry)" if lang == "en" else "（分析失败，请重试）"
    return {
        "positive_pct": 0, "negative_pct": 0, "neutral_pct": 100,
        "sentiment_explanation": msg,
        "top_positive_posts": "N/A", "top_negative_posts": "N/A",
        "hot_topics": "N/A", "emergent_events": "N/A", "anomalies": "N/A",
        "gameplay_summary": "N/A",
    }


def analyze_sentiment(posts_summary: str, subreddits: list[str], lang: str = "zh") -> dict:
    sub_names = " + ".join(f"r/{s}" for s in subreddits)
    if lang == "en":
        system = _SYSTEM_EN
        json_hint = _JSON_HINT_EN
        user_prompt = (
            f"Here is today's post data from {sub_names} (sorted by impact score), "
            f"please analyse the community sentiment:\n\n{posts_summary}"
        )
    else:
        system = _SYSTEM_ZH
        json_hint = _JSON_HINT_ZH
        user_prompt = (
            f"以下是今日 {sub_names} 的帖子数据（已按影响力排序），请分析社区情绪：\n\n"
            f"{posts_summary}"
        )

    # 第 1 轮：function calling
    raw = None
    try:
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
        choice = response.choices[0]
        if choice.message.tool_calls:
            raw = choice.message.tool_calls[0].function.arguments
        else:
            raw = choice.message.content
    except Exception as e:  # 网络/额度等
        print(f"  [WARN] DeepSeek function calling 请求失败（{lang}）：{e}")

    data = _parse(raw)
    if data:
        return _normalise(data, lang)
    print(f"  [WARN] DeepSeek function calling 输出无法解析（{lang}），改用 JSON 模式重试。"
          f"原始：{(raw or '')[:200]}")

    # 第 2 轮：json_object 模式
    raw2 = None
    try:
        response = _client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system + "\n" + json_hint},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=8192,
        )
        raw2 = response.choices[0].message.content
    except Exception as e:
        print(f"  [WARN] DeepSeek JSON 模式请求失败（{lang}）：{e}")

    data = _parse(raw2)
    if data:
        return _normalise(data, lang)

    print(f"  [ERROR] DeepSeek 两轮都无法解析（{lang}），使用降级结果。"
          f"原始：{(raw2 or '')[:200]}")
    return _fallback(lang)
