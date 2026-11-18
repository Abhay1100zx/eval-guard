"""Drift alerts. Two optional channels, both off until they are set in .env:

  ALERT_WEBHOOK_URL                                   a Slack or Discord incoming-webhook URL
  ALERT_SMTP_HOST (+ ALERT_SMTP_PORT/USER/PASSWORD,
  ALERT_EMAIL_FROM) and ALERT_EMAIL_TO                email

An alert that can't be delivered never breaks a run: send_alert() reports what happened per channel instead of raising,
and its messages never include the webhook URL (it contains a secret).
"""
import smtplib
from email.message import EmailMessage
from typing import Any, Dict, Tuple

import requests

from evalguard.config import settings
from evalguard.domains import DOMAINS_REGISTRY

_METRIC_LABELS = {"faithfulness_score": "Faithfulness", "relevance_score": "Relevance", "hit_rate": "Retrieval hit rate",
                  "latency_ms": "Latency"}


def channels() -> Dict[str, bool]:
    """Which channels are configured."""
    return {"webhook": bool(settings.ALERT_WEBHOOK_URL.strip()),
            "email": bool(settings.ALERT_SMTP_HOST.strip() and settings.ALERT_EMAIL_TO.strip())}


def _why(e: Exception) -> str:
    """A safe one-line reason: requests' own messages contain the full webhook URL."""
    status = getattr(getattr(e, "response", None), "status_code", None)
    detail = f" (HTTP {status})" if status else ""
    if isinstance(e, requests.RequestException):
        return f"failed: {type(e).__name__}{detail}"
    return f"failed: {type(e).__name__}: {str(e)[:100]}"


def _send_webhook(text: str) -> None:
    # "text" is what Slack reads, "content" is what Discord reads; each ignores the other
    requests.post(settings.ALERT_WEBHOOK_URL, json={"text": text, "content": text}, timeout=10).raise_for_status()


def _send_email(subject: str, text: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.ALERT_EMAIL_FROM or settings.ALERT_SMTP_USER or "evalguard@localhost"
    msg["To"] = settings.ALERT_EMAIL_TO
    msg.set_content(text)
    port = settings.ALERT_SMTP_PORT
    with (smtplib.SMTP_SSL if port == 465 else smtplib.SMTP)(settings.ALERT_SMTP_HOST, port, timeout=15) as smtp:
        if port != 465:
            smtp.starttls()
        if settings.ALERT_SMTP_USER:
            smtp.login(settings.ALERT_SMTP_USER, settings.ALERT_SMTP_PASSWORD)
        smtp.send_message(msg)


def send_alert(subject: str, text: str) -> Dict[str, str]:
    """Send to every configured channel. Returns {"webhook": "sent" | "failed: ...", "email": ...}; empty if none is set up."""
    on = channels()
    out: Dict[str, str] = {}
    for name, send in (("webhook", lambda: _send_webhook(f"{subject}\n{text}")), ("email", lambda: _send_email(subject, text))):
        if not on[name]:
            continue
        try:
            send()
            out[name] = "sent"
        except Exception as e:
            out[name] = _why(e)
    return out


def _fmt(metric: str, value: float) -> str:
    return f"{value:.0f} ms" if metric == "latency_ms" else f"{value * 100:.1f}%"


def drift_message(run: Dict[str, Any], report: Dict[str, Any]) -> Tuple[str, str]:
    """(subject, body) for a run whose drift report says DRIFT_DETECTED."""
    cfg = DOMAINS_REGISTRY.get(run.get("domain", ""))
    domain = f"{cfg.icon} {cfg.name}" if cfg else run.get("domain", "unknown domain")
    lines = [f"• {_METRIC_LABELS.get(k, k)}: {_fmt(k, m['baseline_mean'])} → {_fmt(k, m['current_mean'])}"
             for k, m in report.get("metrics", {}).items() if m.get("drift_detected")]
    body = [f"Run: {run.get('run_name', run.get('id'))}", f"Model: {run.get('model_name', 'unknown')}", *lines,
            "", report.get("recommendation", "")]
    if settings.WEB_URL and run.get("id"):
        body += ["", f"Open the run: {settings.WEB_URL}/runs/{run['id']}"]
    return f"⚠️ EvalGuard: quality drift in {domain}", "\n".join(body).strip()


def notify_drift(run: Dict[str, Any], report: Dict[str, Any]) -> Dict[str, str]:
    """Alert if (and only if) the report found drift."""
    if not report or report.get("overall_status") != "DRIFT_DETECTED":
        return {}
    return send_alert(*drift_message(run, report))
