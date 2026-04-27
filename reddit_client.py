"""
Reddit 数据抓取。
- 有 REDDIT_CLIENT_ID/SECRET 时：用 OAuth 认证（支持云端/数据中心 IP，如 GitHub Actions）
- 无凭证时：用匿名 JSON 接口（仅本地/家庭 IP 可用）
"""
import time
import requests
from datetime import datetime, timezone, timedelta
from config import REDDIT_USER_AGENT, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET

_JSON_BASE  = "https://www.reddit.com"
_OAUTH_BASE = "https://oauth.reddit.com"


def _get_token() -> str:
    resp = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": REDDIT_USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _make_headers() -> tuple[dict, str]:
    """返回 (headers, base_url)。有凭证用 OAuth，否则用匿名 JSON。"""
    if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
        token = _get_token()
        return {"Authorization": f"Bearer {token}", "User-Agent": REDDIT_USER_AGENT}, _OAUTH_BASE
    return {"User-Agent": REDDIT_USER_AGENT, "Accept": "application/json"}, _JSON_BASE


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
    headers, base = _make_headers()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    results = []

    for sub_name in subreddits:
        after = None
        for _ in range(10):
            params = {"limit": 100, "raw_json": 1}
            if after:
                params["after"] = after

            resp = requests.get(
                f"{base}/r/{sub_name}/new.json",
                params=params,
                headers=headers,
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
                    continue
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
                    "url": f"https://reddit.com{p['permalink']}",
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
            if not after or not page_has_new:
                break
            time.sleep(1)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def get_subreddit_metrics(subreddits: list[str]) -> dict:
    headers, base = _make_headers()
    total_subscribers = 0
    total_active = 0
    details = []

    for name in subreddits:
        resp = requests.get(
            f"{base}/r/{name}/about.json",
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        d = resp.json()["data"]
        subs   = d.get("subscribers", 0)
        active = d.get("active_user_count", 0)
        total_subscribers += subs
        total_active      += active
        details.append({"name": name, "subscribers": subs, "active_users": active})
        time.sleep(0.5)

    return {
        "total_subscribers": total_subscribers,
        "total_active_users": total_active,
        "subreddit_details": details,
    }
