"""
通过 SMTP 发送邮件报告（默认 Gmail）。
可在 GitHub Actions（Linux）等无本机 Outlook 的环境运行：
用 SMTP_USER / SMTP_PASSWORD 登录发件，报告仍发送到 REPORT_EMAIL_TO 指定的收件人。
若未配置收件人或 SMTP 凭证，则打印到 stdout（dry-run 模式）。
"""
import re
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from config import REPORT_EMAIL_TO, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD


def _to_html(text: str) -> str:
    lines = text.split("\n")
    html_lines = []
    for line in lines:
        if re.match(r"^—{10,}$", line.strip()):
            html_lines.append('<hr style="border:none;border-top:1px solid #ddd;margin:14px 0">')
            continue
        line = re.sub(r"\*(.+?)\*", r"<b>\1</b>", line)
        line = re.sub(r"_(.+?)_", r"<i>\1</i>", line)
        html_lines.append(line + "<br>")

    return (
        '<html><body style="font-family:Arial,sans-serif;font-size:14px;'
        'line-height:1.8;max-width:760px;padding:24px;color:#333">'
        + "\n".join(html_lines)
        + "</body></html>"
    )


def _recipients(raw: str) -> list[str]:
    """支持用分号或逗号分隔多个收件人。"""
    return [a.strip() for a in re.split(r"[;,]", raw or "") if a.strip()]


def send(text: str, subject: str = "FC Mobile 社区舆情日报") -> None:
    recipients = _recipients(REPORT_EMAIL_TO)
    if not recipients or not SMTP_USER or not SMTP_PASSWORD:
        print("\n" + "=" * 60)
        print(text)
        print("=" * 60)
        print("\n[Notifier] REPORT_EMAIL_TO / SMTP_USER / SMTP_PASSWORD 未完整配置，报告已打印到 stdout。")
        return

    msg = MIMEText(_to_html(text), "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr(("FC Sentiment Monitor", SMTP_USER))
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, recipients, msg.as_string())

    print(f"邮件已发送至 {', '.join(recipients)}")
