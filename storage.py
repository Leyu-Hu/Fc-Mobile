"""
对应原步骤 6（查找昨日数据）和步骤 8（保存今日数据）。
用本地 JSON 文件替代 Google Sheets，保留最近 30 天记录。
namespace 参数区分不同类型的指标（如 "sub"、"post"）。
"""
import json
import os
from datetime import datetime, timezone, timedelta
from config import DATA_DIR, METRICS_FILE


def _key(delta_days: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=delta_days)).strftime("%Y-%m-%d")


def load_metrics(namespace: str = "default", date_key: str = None) -> dict:
    """读取指定命名空间下指定日期（默认昨天）的指标，不存在则返回空 dict。"""
    if not os.path.exists(METRICS_FILE):
        return {}
    with open(METRICS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    ns_data = data.get(namespace, {})
    return ns_data.get(date_key or _key(1), {})


def save_metrics(metrics: dict, date_key: str = None, namespace: str = "default") -> None:
    """保存今日指标，自动清理 30 天前的旧数据。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    existing = {}
    if os.path.exists(METRICS_FILE):
        with open(METRICS_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)

    key = date_key or _key(0)
    if namespace not in existing:
        existing[namespace] = {}
    existing[namespace][key] = metrics

    # 每个 namespace 只保留最近 30 天
    cutoff = _key(30)
    for ns in existing:
        existing[ns] = {k: v for k, v in existing[ns].items() if k >= cutoff}

    with open(METRICS_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
