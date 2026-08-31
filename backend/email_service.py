"""
LUNARIS Email Dispatcher (Resend Integration)
Runs securely on the backend ONLY. Never exposes RESEND_API_KEY to frontend.
"""

import os
import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, Any

logger = logging.getLogger("lunaris.email")

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")

DEPARTMENT_EMAILS = {
    "Road Maintenance Department": "roads@kmcgov.in",
    "Drainage Department": "drainage@kmcgov.in",
    "Traffic Department": "traffic@kolkatapolice.gov.in",
    "Urban Infrastructure": "infra@kmcgov.in"
}

def send_authority_alert_email(
    department_name: str,
    incident_id: str,
    defect_type: str,
    location: str,
    severity: str,
    confidence: float,
    evidence_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Sends an email notification to the assigned municipal department.
    If RESEND_API_KEY is missing or unconfigured, logs and returns status without throwing.
    """
    recipient = DEPARTMENT_EMAILS.get(department_name, "roads@kmcgov.in")

    if not RESEND_API_KEY:
        logger.info(f"[EMAIL SERVICE NOT CONFIGURED] Skipping email for {incident_id} to {recipient}. Internal notifications active.")
        return {
            "status": "SKIPPED",
            "message": "EMAIL SERVICE NOT CONFIGURED"
        }

    subject = f"🚨 [{severity}] {defect_type.upper()} Alert — {incident_id} at {location}"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; background-color: #0c1322; color: #ffffff; padding: 24px; border-radius: 12px;">
      <h2 style="color: #00e5ff; margin-bottom: 8px;">LUNARIS — Urban Intelligence Incident Dispatch</h2>
      <p style="color: #94a3b8; font-size: 14px;">Automated Municipal Work Order Notification</p>
      
      <div style="background-color: #121b2d; padding: 18px; border-radius: 8px; border-left: 4px solid {'#ef4444' if severity == 'CRITICAL' else '#f59e0b'}; margin: 18px 0;">
        <p><strong>Incident ID:</strong> {incident_id}</p>
        <p><strong>Defect Type:</strong> {defect_type}</p>
        <p><strong>Severity:</strong> <span style="color: {'#ef4444' if severity == 'CRITICAL' else '#f59e0b'}; font-weight: bold;">{severity}</span></p>
        <p><strong>Location:</strong> {location}</p>
        <p><strong>AI Confidence:</strong> {confidence:.1f}%</p>
        <p><strong>Assigned Authority:</strong> {department_name} ({recipient})</p>
      </div>

      {'<p><a href="' + evidence_url + '" style="background-color: #00e5ff; color: #000000; padding: 10px 18px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">View Visual Evidence</a></p>' if evidence_url else ''}
      
      <p style="color: #64748b; font-size: 12px; margin-top: 24px;">Smart City Road Asset Management System &bull; Kolkata Command Center</p>
    </div>
    """

    payload = {
        "from": "LUNARIS Alerts <alerts@lunaris-urban.gov>",
        "to": [recipient],
        "subject": subject,
        "html": html_content
    }

    try:
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=json.dumps(payload).encode('utf-8'),
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            logger.info(f"Alert email dispatched to {recipient} via Resend. Status: {resp.status}")
            return {"status": "SENT", "recipient": recipient}
    except urllib.error.HTTPError as he:
        logger.warning(f"Resend HTTP error {he.code}: {he.read().decode('utf-8', errors='ignore')}")
        return {"status": "FAILED", "code": he.code}
    except Exception as e:
        logger.warning(f"Email dispatch note: {e}")
        return {"status": "ERROR", "error": str(e)}
