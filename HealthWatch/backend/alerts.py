"""Early-warning alerts: stored in the database and optionally e-mailed."""
import logging
import os
import smtplib
import threading
from email.message import EmailMessage

log = logging.getLogger(__name__)


def _send_email(host, port, user, password, recipients, subject, body):
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = ", ".join(recipients)
        msg.set_content(body)
        with smtplib.SMTP(host, port, timeout=8) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(msg)
        log.info("Alert e-mail sent to %s", recipients)
    except Exception:  # never let a mail problem break data entry
        log.exception("Could not send alert e-mail")


def email_configured() -> bool:
    return all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "ALERT_EMAIL_TO"))


def create_alert(db, record_id, village_id, assessment, village_name, report_date,
                 diarrhea, fever, notify=True):
    message = (
        f"{village_name}: {assessment['level']} risk (score {assessment['score']}/{assessment['max_score']}). "
        f"{diarrhea} diarrhea and {fever} fever cases reported on {report_date}."
    )
    if assessment["rising"]:
        message += " Cases are rising."
    emailed = 0
    if notify and email_configured():
        recipients = [e.strip() for e in os.environ["ALERT_EMAIL_TO"].split(",") if e.strip()]
        body = message + "\n\nRecommended action: " + assessment["advice"]
        threading.Thread(
            target=_send_email,
            args=(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 587)),
                  os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"], recipients,
                  f"[HealthWatch] {assessment['level']} risk in {village_name}", body),
            daemon=True,
        ).start()
        emailed = 1
    db.execute(
        "INSERT INTO alerts (record_id, village_id, level, message, emailed) VALUES (?,?,?,?,?)",
        (record_id, village_id, assessment["level"], message, emailed),
    )
