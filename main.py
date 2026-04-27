"""
主流程：按分组抓取 Google Play 评论、分析情绪、分别发送邮件。

运行方式：
  python main.py            # 所有分组
  python main.py --dry-run  # 只打印，不发邮件
  python main.py --group "FC Mobile"  # 只跑指定分组
"""
import sys
import datetime
from config import MONITOR_GROUPS
from reviews_client import get_recent_reviews, get_app_metrics
from analyzer import analyze_sentiment
from storage import load_metrics, save_metrics
import notifier


def _growth_str(today: dict, yesterday: dict, key: str) -> str:
    t = today.get(key, 0)
    y = yesterday.get(key, 0)
    if not isinstance(t, (int, float)):
        return "N/A"
    if y == 0:
        return "首次记录" if t == 0 else "新增"
    return f"{(t - y) / y * 100:+.1f}%"


def _build_reviews_summary(reviews_list: list[dict], limit: int = 60) -> str:
    if not reviews_list:
        return "（今日无有效评论数据）"
    lines = []
    for r in reviews_list[:limit]:
        stars = "⭐" * r["stars"]
        lines.append(
            f"[分值:{r['score']:.0f}] {stars} 👍{r['thumbs_up']} [{r['lang']}] {r['author']}\n"
            f"  {r['body']}\n"
            f"  {r['url']}"
        )
    return "\n\n---\n\n".join(lines)


def _build_report(
    group_name: str,
    app_ids: list[str],
    sentiment: dict,
    today_app: dict,
    yesterday_app: dict,
    today_review: dict,
    yesterday_review: dict,
    report_date: str,
) -> str:
    g_review = lambda k: _growth_str(today_review, yesterday_review, k)

    app_lines = "\n".join(
        f"  • {d['title']}：⭐{d['score']}/5.0  ({d['ratings']:,} 总评分)  下载量：{d['installs']}"
        for d in today_app.get("app_details", [])
    ) or "  （无数据）"

    return f"""*【{group_name} 玩家口碑日报】*
数据来源：Google Play（英文 + 日文）
报告时间：{report_date}
{"—" * 30}
*1. 情绪概览*
• 积极：{sentiment.get('positive_pct', 'N/A')}%  消极：{sentiment.get('negative_pct', 'N/A')}%  中立：{sentiment.get('neutral_pct', 'N/A')}%
• 今日评论平均星级：⭐{sentiment.get('avg_stars', 'N/A')}/5.0
{sentiment.get('sentiment_explanation', '')}

*2. 高影响力正面评论*
{sentiment.get('top_positive_reviews', '暂无')}

*3. 高影响力负面评论*
{sentiment.get('top_negative_reviews', '暂无')}

*4. 玩家集中反映的问题*
{sentiment.get('hot_topics', '暂无')}

*5. 突发事件 / 新兴关注点*
{sentiment.get('emergent_events', '暂无')}

*6. 异常情况*
{sentiment.get('anomalies', '暂无')}

{"—" * 30}
*7. 应用商店数据*
{app_lines}

*今日评论概况（过去 24h）*
• 有效评论数：{today_review.get('review_count', 0)}（{g_review('review_count')}）
• 平均星级：{today_review.get('avg_stars', 0):.1f}（{g_review('avg_stars')}）
• 1-2星占比：{today_review.get('negative_pct', 0):.0f}%（{g_review('negative_pct')}）
{"—" * 30}
_影响力分值 = 星级×2 + 点赞×0.5 | 情绪分析由 DeepSeek AI 生成，仅供参考_"""


def _run_group(group: dict, report_date: str, date_str: str, dry_run: bool) -> None:
    name    = group["name"]
    app_ids = group["subreddits"]  # 字段名沿用，实际存放 app ID
    ns      = name.replace(" ", "_")

    print(f"\n{'='*40}")
    print(f"  处理分组：{name}")
    print(f"  App IDs：{', '.join(app_ids)}")
    print(f"{'='*40}")

    print("[1/4] 抓取 Google Play 评论...")
    review_list = get_recent_reviews(app_ids, hours=24)
    print(f"      有效评论：{len(review_list)} 条")

    print("[2/4] DeepSeek 情绪分析...")
    sentiment = analyze_sentiment(_build_reviews_summary(review_list), name)

    print("[3/4] 获取应用评分数据...")
    today_app    = get_app_metrics(app_ids)
    neg_reviews  = [r for r in review_list if r["stars"] <= 2]
    today_review = {
        "review_count": len(review_list),
        "avg_stars":    sum(r["stars"] for r in review_list) / len(review_list) if review_list else 0,
        "negative_pct": len(neg_reviews) / len(review_list) * 100 if review_list else 0,
    }

    yesterday_app    = load_metrics(namespace=f"{ns}_app")
    yesterday_review = load_metrics(namespace=f"{ns}_review")
    save_metrics(today_app,    namespace=f"{ns}_app")
    save_metrics(today_review, namespace=f"{ns}_review")

    report = _build_report(
        name, app_ids, sentiment,
        today_app, yesterday_app,
        today_review, yesterday_review,
        report_date,
    )

    if dry_run:
        print(f"\n[DRY RUN] {name} 报告：\n")
        print(report)
    else:
        subject = f"{name} 玩家口碑日报 {date_str}"
        print(f"[4/4] 发送邮件：{subject}")
        notifier.send(report, subject=subject)


def run(dry_run: bool = False, only_group: str = None) -> None:
    now_sg      = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    report_date = now_sg.strftime("%Y年%m月%d日 %H:%M SGT")
    date_str    = now_sg.strftime("%Y-%m-%d")

    groups = MONITOR_GROUPS
    if only_group:
        groups = [g for g in groups if g["name"] == only_group]
        if not groups:
            print(f"未找到分组「{only_group}」，可用：{[g['name'] for g in MONITOR_GROUPS]}")
            return

    for group in groups:
        _run_group(group, report_date, date_str, dry_run)

    print("\n全部分组处理完毕。")


if __name__ == "__main__":
    dry_run    = "--dry-run" in sys.argv
    only_group = None
    if "--group" in sys.argv:
        idx = sys.argv.index("--group")
        only_group = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
    run(dry_run=dry_run, only_group=only_group)
