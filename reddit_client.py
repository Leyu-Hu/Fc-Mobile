"""
使用 Arctic Shift 归档 API 获取帖子（免认证、不被 Reddit 403 屏蔽）。
订阅指标通过 Reddit about.json 获取（User-Agent 含联系邮箱，符合 Reddit 规范）。
"""
import time
import requests
from datetime import datetime, timezone, timedelta

_ARCTIC_BASE = "https://arctic-shift.photon-reddit.com/api"
_REDDIT_BASE = "https://www.reddit.com"
_HEADERS = {
    "User-Agent": "FCMobile Sentiment Monitor v1.0 (by leyu.hu1501@gmail.com)",
    "Accept": "application/json",
}


def _score(post: dict) -> float:
    return post.get("score", 0) * 1 + post.get("num_comments", 0) * 3


def _is_low_quality(post: dict) -> bool:
    if post.get("stickied"):
        return True
    if post.get("score", 0) < -5:
        return True
    if len((post.get("title") or "").strip()) < 8:
        return True
    return False


def get_recent_posts(subreddits: list[str], hours: int = 24) -> list[dict]:
    """
    从 Arctic Shift 拉取过去 N 小时的帖子，过滤低质量内容后合并排序。
    每个 subreddit 最多翻 10 页（1000 条）。
    """
    cutoff_ts = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp())
    now_ts    = int(datetime.now(timezone.utc).timestamp())
    results   = []

    for sub_name in subreddits:
        after_ts = cutoff_ts

        for _ in range(10):
            params = {
                "subreddit": sub_name,
                "after":     after_ts,
                "before":    now_ts,
                "limit":     100,
                "sort":      "asc",
            }

            try:
                resp = requests.get(
                    f"{_ARCTIC_BASE}/posts/search",
                    params=params,
                    headers=_HEADERS,
                    timeout=20,
                )
            except requests.ConnectionError:
                print(f"  Arctic Shift 连接失败，跳过 r/{sub_name}")
                break

            if resp.status_code == 429:
                print("  触发限速（429），等待 10 秒...")
                time.sleep(10)
                continue
            if not resp.ok:
                print(f"  Arctic Shift HTTP {resp.status_code}，跳过 r/{sub_name}")
                break

            posts = resp.json().get("data", [])
            if not posts:
                break

            for p in posts:
                if _is_low_quality(p):
                    continue
                body = (p.get("selftext") or "").strip()
                if body in ("[removed]", "[deleted]"):
                    body = ""
                created_ts = p.get("created_utc", 0)
                results.append({
                    "id":           p.get("id", ""),
                    "title":        p.get("title", ""),
                    "body":         body[:300],
                    "url":          f"https://reddit.com{p.get('permalink', '')}",
                    "author":       p.get("author", "[deleted]"),
                    "subreddit":    p.get("subreddit", sub_name),
                    "score":        _score(p),
                    "upvotes":      p.get("score", 0),
                    "upvote_ratio": round(p.get("upvote_ratio", 1.0), 2),
                    "num_comments": p.get("num_comments", 0),
                    "flair":        p.get("link_flair_text") or "",
                    "created_utc":  datetime.fromtimestamp(
                        created_ts, tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ") if created_ts else "",
                })

            last_ts = posts[-1].get("created_utc", 0)
            if not last_ts or last_ts >= now_ts or len(posts) < 100:
                break
            after_ts = last_ts + 1
            time.sleep(0.8)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def get_subreddit_metrics(subreddits: list[str]) -> dict:
    """获取各 subreddit 订阅数和当前在线人数。"""
    total_subscribers = 0
    total_active = 0
    details = []

    for name in subreddits:
        try:
            resp = requests.get(
                f"{_REDDIT_BASE}/r/{name}/about.json",
                headers=_HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            d = resp.json()["data"]
            subs   = d.get("subscribers", 0)
            active = d.get("active_user_count", 0)
        except Exception as e:
            print(f"  获取 r/{name} 指标失败：{e}，使用 0 代替")
            subs, active = 0, 0

        total_subscribers += subs
        total_active      += active
        details.append({"name": name, "subscribers": subs, "active_users": active})
        time.sleep(0.5)

    return {
        "total_subscribers":  total_subscribers,
        "total_active_users": total_active,
        "subreddit_details":  details,
    }
