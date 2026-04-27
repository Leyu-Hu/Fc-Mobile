"""
通过 Gmail SMTP 发送邮件报告。
本地和 GitHub Actions 均可使用，无需安装 Outlook。
"""
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import REPORT_EMAIL_TO, SMTP_USER, SMTP_PASSWORD


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


def send(text: str, subject: str = "FC Mobile 社区舆情日报") -> None:
    if not REPORT_EMAIL_TO or not SMTP_USER or not SMTP_PASSWORD:
        print("\n" + "=" * 60)
        print(text)
        print("=" * 60)
        print("\n[Notifier] SMTP 未配置，报告已打印到 stdout。")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = REPORT_EMAIL_TO
    msg.attach(MIMEText(_to_html(text), "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, REPORT_EMAIL_TO, msg.as_string())

    print(f"邮件已发送：{SMTP_USER} → {REPORT_EMAIL_TO}")
