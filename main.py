"""
主流程：按分组分别抓取、分析、发送独立邮件。

运行方式：
  python main.py            # 立即执行一次（发送所有分组邮件）
  python main.py --dry-run  # 跳过邮件，只打印报告
  python main.py --group "FC Mobile"   # 只跑指定分组

定时运行（每天 09:00 SGT = UTC 01:00）：
  cron: 0 1 * * * cd /path/to/sentiment_monitor && PYTHONUTF8=1 python main.py
"""
import sys
import datetime
from config import MONITOR_GROUPS
from reddit_client import get_recent_posts, get_subreddit_metrics
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


def _build_posts_summary(posts: list[dict], limit: int = 50) -> str:
    if not posts:
        return "（今日无有效帖子数据）"
    lines = []
    for p in posts[:limit]:
        flair = f"[{p['flair']}] " if p.get("flair") else ""
        body_preview = f"\n  内容：{p['body']}" if p.get("body") else ""
        lines.append(
            f"[分值:{p['score']:.0f}] r/{p['subreddit']} | {flair}u/{p['author']}\n"
            f"  标题：{p['title']}{body_preview}\n"
            f"  ⬆️{p['upvotes']} ({int(p['upvote_ratio']*100)}%) 💬{p['num_comments']}\n"
            f"  URL: {p['url']}"
        )
    return "\n\n---\n\n".join(lines)


def _build_report(
    group_name: str,
    subreddits: list[str],
    sentiment: dict,
    today_sub: dict,
    yesterday_sub: dict,
    today_post: dict,
    yesterday_post: dict,
    report_date: str,
) -> str:
    g_sub  = lambda k: _growth_str(today_sub, yesterday_sub, k)
    g_post = lambda k: _growth_str(today_post, yesterday_post, k)

    sub_lines = "\n".join(
        f"  • r/{d['name']}：{d['subscribers']:,} 订阅 | {d['active_users']} 在线"
        for d in today_sub.get("subreddit_details", [])
    ) or "  （无数据）"

    sub_names = " + ".join(f"r/{s}" for s in subreddits)

    return f"""*【{group_name} 社区舆情日报】*
监控范围：{sub_names}
报告时间：{report_date}
{"—" * 30}
*1. 情绪概览*
• 积极：{sentiment.get('positive_pct', 'N/A')}%  消极：{sentiment.get('negative_pct', 'N/A')}%  中立：{sentiment.get('neutral_pct', 'N/A')}%
{sentiment.get('sentiment_explanation', '')}

*2. 高影响力正面帖子*
{sentiment.get('top_positive_posts', '暂无')}

*3. 高影响力负面帖子*
{sentiment.get('top_negative_posts', '暂无')}

*4. 热门话题*
{sentiment.get('hot_topics', '暂无')}

*5. 突发事件 / 新兴关注点*
{sentiment.get('emergent_events', '暂无')}

*6. 异常情况*
{sentiment.get('anomalies', '暂无')}

{"—" * 30}
*7. 社区规模数据*
{sub_lines}
• 合计订阅：{today_sub.get('total_subscribers', 0):,}（{g_sub('total_subscribers')}）
• 当前在线：{today_sub.get('total_active_users', 0):,}

*今日帖子概况（过去 24h）*
• 有效帖子数：{today_post.get('post_count', 0)}（{g_post('post_count')}）
• 平均分值：{today_post.get('avg_score', 0):.1f}（{g_post('avg_score')}）
• 总评论数：{today_post.get('total_comments', 0):,}（{g_post('total_comments')}）
{"—" * 30}
_影响力分值 = 点赞×1 + 评论×3 | 情绪分析由 DeepSeek AI 生成，仅供参考_"""


def _run_group(group: dict, report_date: str, date_str: str, dry_run: bool) -> None:
    name = group["name"]
    subreddits = group["subreddits"]
    ns = name.replace(" ", "_")  # 存储时用作 namespace，避免空格

    print(f"\n{'='*40}")
    print(f"  处理分组：{name}  ({' + '.join(subreddits)})")
    print(f"{'='*40}")

    print(f"[1/4] 抓取帖子...")
    posts = get_recent_posts(subreddits, hours=24)
    print(f"      有效帖子：{len(posts)} 条")

    print(f"[2/4] DeepSeek 情绪分析...")
    sentiment = analyze_sentiment(_build_posts_summary(posts), subreddits)

    print(f"[3/4] 获取订阅指标...")
    today_sub  = get_subreddit_metrics(subreddits)
    today_post = {
        "post_count":     len(posts),
        "avg_score":      sum(p["score"] for p in posts) / len(posts) if posts else 0,
        "total_comments": sum(p["num_comments"] for p in posts),
    }
    yesterday_sub  = load_metrics(namespace=f"{ns}_sub")
    yesterday_post = load_metrics(namespace=f"{ns}_post")
    save_metrics(today_sub,  namespace=f"{ns}_sub")
    save_metrics(today_post, namespace=f"{ns}_post")

    report = _build_report(
        name, subreddits, sentiment,
        today_sub, yesterday_sub,
        today_post, yesterday_post,
        report_date,
    )

    if dry_run:
        print(f"\n[DRY RUN] {name} 报告：\n")
        print(report)
    else:
        subject = f"{name} 社区舆情日报 {date_str}"
        print(f"[4/4] 发送邮件：{subject}")
        notifier.send(report, subject=subject)


def run(dry_run: bool = False, only_group: str = None) -> None:
    now_sg    = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    report_date = now_sg.strftime("%Y年%m月%d日 %H:%M SGT")
    date_str    = now_sg.strftime("%Y-%m-%d")

    groups = MONITOR_GROUPS
    if only_group:
        groups = [g for g in groups if g["name"] == only_group]
        if not groups:
            print(f"未找到分组「{only_group}」，可用分组：{[g['name'] for g in MONITOR_GROUPS]}")
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
