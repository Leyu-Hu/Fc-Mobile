import os
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

REPORT_EMAIL_TO = os.environ.get("REPORT_EMAIL_TO", "")
SMTP_USER     = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

REDDIT_USER_AGENT    = "FCMobile Sentiment Monitor v1.0"
REDDIT_CLIENT_ID     = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")

DATA_DIR     = os.path.join(os.path.dirname(__file__), "data")
METRICS_FILE = os.path.join(DATA_DIR, "daily_metrics.json")


def _parse_groups(raw: str) -> list[dict]:
    groups = []
    for part in raw.split("|"):
        part = part.strip()
        if ":" not in part:
            continue
        name, subs_str = part.split(":", 1)
        subs = [s.strip() for s in subs_str.split(",") if s.strip()]
        if name.strip() and subs:
            groups.append({"name": name.strip(), "subreddits": subs})
    return groups


MONITOR_GROUPS = _parse_groups(
    os.environ.get("MONITOR_GROUPS", "FC Mobile:FUTMobile|eFootball:eFootball")
)
