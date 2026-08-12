import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

logging.basicConfig(level=logging.INFO)

# Configuration - Update with your SMTP Relay details or SMTP credentials
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "your-alerts-email@gmail.com"  # Sender Email
SMTP_PASS = "your-app-password"            # App Password or Token
ALERT_RECIPIENTS = ["tech-lead@company.com", "on-duty-desk@company.com"]

def send_critical_alert(hostname: str, ip_address: str, user: str, issue: str, tech_portal_url: str = "http://localhost:8080/tech"):
    """
    Sends a styled HTML email alert strictly for CRITICAL endpoint state transitions.
    """
    subject = f"🚨 [CRITICAL ALERT] FleetPulse Endpoint Required Action: {hostname}"

    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #1e293b; border: 1px solid #dc2626; border-radius: 8px; padding: 24px;">
            <h2 style="color: #ef4444; margin-top: 0;">🚨 CRITICAL Endpoint Exception Detected</h2>
            <p style="color: #cbd5e1;">FleetPulse Control Plane detected a critical issue requiring technician dispatch.</p>
            
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0; background-color: #0f172a; border-radius: 6px;">
                <tr>
                    <td style="padding: 10px; font-weight: bold; color: #94a3b8;">Hostname:</td>
                    <td style="padding: 10px; color: #ffffff;">{hostname}</td>
                </tr>
                <tr style="border-top: 1px solid #334155;">
                    <td style="padding: 10px; font-weight: bold; color: #94a3b8;">IP Address:</td>
                    <td style="padding: 10px; color: #ffffff;">{ip_address}</td>
                </tr>
                <tr style="border-top: 1px solid #334155;">
                    <td style="padding: 10px; font-weight: bold; color: #94a3b8;">Logged User:</td>
                    <td style="padding: 10px; color: #ffffff;">{user}</td>
                </tr>
                <tr style="border-top: 1px solid #334155;">
                    <td style="padding: 10px; font-weight: bold; color: #ef4444;">Critical Condition:</td>
                    <td style="padding: 10px; color: #fca5a5; font-weight: bold;">{issue}</td>
                </tr>
            </table>

            <div style="text-align: center; margin-top: 25px;">
                <a href="{tech_portal_url}" style="background-color: #dc2626; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Open Tech Portal & Remediate</a>
            </div>
            
            <p style="font-size: 11px; color: #64748b; margin-top: 30px; text-align: center;">
                Automated notification from FleetPulse RMM Engine • Do not reply directly to this message.
            </p>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"FleetPulse SOC <{SMTP_USER}>"
    msg["To"] = ", ".join(ALERT_RECIPIENTS)
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, ALERT_RECIPIENTS, msg.as_string())
        logging.info(f"Critical email alert successfully dispatched for {hostname}")
        return True
    except Exception as e:
        logging.error(f"Failed to dispatch critical alert email for {hostname}: {e}")
        return False