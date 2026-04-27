"""
通过 google-play-scraper 获取 Google Play 评论和应用评分。
无需任何 API key，GitHub Actions 可正常访问。
"""
from datetime import datetime, timezone, timedelta
from google_play_scraper import reviews, Sort, app as gp_app


def _ensure_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get_recent_reviews(app_ids: list[str], hours: int = 24) -> list[dict]:
    """
    获取多个 App 过去 N 小时的最新评论。
    每个 App 分别拉取英文和日文评论，合并去重后返回。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    results = []
    seen = set()

    for app_id in app_ids:
        for lang, country in [("en", "us"), ("ja", "jp")]:
            result, _ = reviews(
                app_id,
                lang=lang,
                country=country,
                sort=Sort.NEWEST,
                count=200,
            )
            for r in result:
                review_time = _ensure_utc(r["at"])
                if review_time < cutoff:
                    continue

                content = (r.get("content") or "").strip()
                if len(content) < 5:
                    continue

                uid = r.get("reviewId", "")
                if uid in seen:
                    continue
                seen.add(uid)

                stars = r["score"]  # 1-5
                thumbs = r.get("thumbsUpCount", 0)
                results.append({
                    "id": uid,
                    "body": content[:400],
                    "author": r.get("userName", "Anonymous"),
                    "app_id": app_id,
                    "stars": stars,
                    "thumbs_up": thumbs,
                    "lang": lang,
                    "score": stars * 2 + thumbs * 0.5,  # 影响力分值
                    "created_utc": review_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "url": f"https://play.google.com/store/apps/details?id={app_id}",
                })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def get_app_metrics(app_ids: list[str]) -> dict:
    """获取各 App 当前综合评分和总评分数。"""
    details = []
    total_ratings = 0

    for app_id in app_ids:
        info = gp_app(app_id, lang="en", country="us")
        rating_count = info.get("ratings", 0)
        total_ratings += rating_count
        details.append({
            "app_id": app_id,
            "title": info.get("title", app_id),
            "score": round(info.get("score") or 0, 2),
            "ratings": rating_count,
            "installs": info.get("installs", "N/A"),
        })

    return {"total_ratings": total_ratings, "app_details": details}
