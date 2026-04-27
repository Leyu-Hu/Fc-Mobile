"""
使用 Reddit 免认证 JSON 接口（无需 API key）获取帖子和社区数据。
Reddit 对带 User-Agent 的请求限速约 60次/分钟，已在翻页间加 sleep 规避。
"""
import time
import requests
from datetime import datetime, timezone, timedelta
from config import REDDIT_USER_AGENT

_HEADERS = {
    "User-Agent": REDDIT_USER_AGENT,
    "Accept": "application/json",
}
_BASE = "https://www.reddit.com"


def _score(post: dict) -> float:
    return post["score"] * 1 + post["num_comments"] * 3


def _is_low_quality(post: dict) -> bool:
    if post.get("stickied"):
        return True
    if post.get("score", 0) < -5:
        return True
    if len(post.get("title", "").strip()) < 8:
        return True
    return False


def get_recent_posts(subreddits: list[str], hours: int = 24) -> list[dict]:
    """
    从各 subreddit 拉取过去 N 小时的新帖，过滤低质量内容后合并排序。
    每个 subreddit 最多翻 10 页（1000 条原始帖子）。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    results = []

    for sub_name in subreddits:
        after = None
        for _ in range(10):
            params = {"limit": 100, "raw_json": 1}
            if after:
                params["after"] = after

            resp = requests.get(
                f"{_BASE}/r/{sub_name}/new.json",
                params=params,
                headers=_HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            children = data.get("children", [])

            if not children:
                break

            page_has_new = False
            for child in children:
                p = child["data"]
                created = datetime.fromtimestamp(p["created_utc"], tz=timezone.utc)
                if created < cutoff:
                    continue  # 跳过超时帖，但继续翻页（API 不保证严格按时间排序）
                page_has_new = True

                if _is_low_quality(p):
                    continue

                body = (p.get("selftext") or "").strip()
                if body in ("[removed]", "[deleted]"):
                    body = ""

                results.append({
                    "id": p["id"],
                    "title": p["title"],
                    "body": body[:300],
                    "url": f"{_BASE}{p['permalink']}",
                    "author": p.get("author", "[deleted]"),
                    "subreddit": p.get("subreddit", sub_name),
                    "score": _score(p),
                    "upvotes": p.get("score", 0),
                    "upvote_ratio": round(p.get("upvote_ratio", 1.0), 2),
                    "num_comments": p.get("num_comments", 0),
                    "flair": p.get("link_flair_text") or "",
                    "created_utc": datetime.fromtimestamp(
                        p["created_utc"], tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

            after = data.get("after")
            # 整页都是旧帖，或没有下一页，停止翻页
            if not after or not page_has_new:
                break
            time.sleep(1)  # 避免触发 Reddit 速率限制

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def get_subreddit_metrics(subreddits: list[str]) -> dict:
    """获取各 subreddit 订阅数和当前在线人数。"""
    total_subscribers = 0
    total_active = 0
    details = []

    for name in subreddits:
        resp = requests.get(
            f"{_BASE}/r/{name}/about.json",
            headers=_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        d = resp.json()["data"]
        subs = d.get("subscribers", 0)
        active = d.get("active_user_count", 0)
        total_subscribers += subs
        total_active += active
        details.append({"name": name, "subscribers": subs, "active_users": active})
        time.sleep(0.5)

    return {
        "total_subscribers": total_subscribers,
        "total_active_users": total_active,
        "subreddit_details": details,
    }
