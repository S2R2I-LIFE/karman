"""
Email Sending Module
Handles email notifications for access requests and approvals
"""

import smtplib
import sqlite3
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional


class EmailConfig:
    """Email configuration from environment variables (used as defaults only)"""
    ENABLED = os.environ.get('EMAIL_ENABLED', 'false').lower() == 'true'
    SMTP_HOST = os.environ.get('SMTP_HOST', 'localhost')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
    SMTP_USE_TLS = os.environ.get('SMTP_USE_TLS', 'true').lower() == 'true'
    FROM_EMAIL = os.environ.get('FROM_EMAIL', 'noreply@custom-cvp.local')
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@custom-cvp.local')


class EmailSender:
    """Email sending functionality"""

    def __init__(self, db_path='custom-cvp.db', config=EmailConfig):
        self.db_path = db_path
        self.config = config
        self._init_settings_table()

    def _init_settings_table(self):
        """Create app_settings table if it doesn't exist"""
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        conn.commit()
        conn.close()

    def get_setting(self, key: str, default: str = '') -> str:
        """Read a setting from the database, falling back to the given default"""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute('SELECT value FROM app_settings WHERE key = ?', (key,)).fetchone()
        conn.close()
        return row[0] if row else default

    def set_setting(self, key: str, value: str):
        """Persist a setting to the database"""
        conn = sqlite3.connect(self.db_path)
        conn.execute('INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)', (key, value))
        conn.commit()
        conn.close()

    def get_email_settings(self) -> dict:
        """Return current email settings (DB overrides env vars)"""
        return {
            'enabled':      self.get_setting('email_enabled',      str(self.config.ENABLED).lower()),
            'smtp_host':    self.get_setting('smtp_host',           self.config.SMTP_HOST),
            'smtp_port':    self.get_setting('smtp_port',           str(self.config.SMTP_PORT)),
            'smtp_username':self.get_setting('smtp_username',       self.config.SMTP_USERNAME),
            'smtp_password':self.get_setting('smtp_password',       self.config.SMTP_PASSWORD),
            'smtp_use_tls': self.get_setting('smtp_use_tls',        str(self.config.SMTP_USE_TLS).lower()),
            'from_email':   self.get_setting('from_email',          self.config.FROM_EMAIL),
        }

    @property
    def enabled(self):
        return self.get_setting('email_enabled', str(self.config.ENABLED).lower()) == 'true'

    @enabled.setter
    def enabled(self, value):
        pass  # ignore constructor assignment; value comes from DB/env

    def send_email(self, to_email: str, subject: str, html_body: str,
                  email_type: str, related_request_id: Optional[int] = None) -> bool:
        """
        Send email with error handling and logging

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body
            email_type: Type of email for logging (access_request, approval, rejection)
            related_request_id: Related access request ID (optional)

        Returns:
            True if successful, False otherwise
        """
        # Log the email attempt
        success = False
        error_message = None

        if not self.enabled:
            print(f"[EMAIL] Disabled - Would send '{subject}' to {to_email}")
            self._log_email(to_email, subject, email_type, True, None, related_request_id)
            return True

        try:
            cfg = self.get_email_settings()
            smtp_host = cfg['smtp_host']
            smtp_port = int(cfg['smtp_port'])
            smtp_user = cfg['smtp_username']
            smtp_pass = cfg['smtp_password']
            use_tls   = cfg['smtp_use_tls'] == 'true'
            from_email = cfg['from_email']

            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = from_email
            msg['To'] = to_email

            # Add HTML body
            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)

            # Connect and send
            server = smtplib.SMTP(smtp_host, smtp_port)
            if use_tls:
                server.starttls()

            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)

            server.send_message(msg)
            server.quit()

            success = True
            print(f"[EMAIL] Sent '{subject}' to {to_email}")

        except Exception as e:
            error_message = str(e)
            print(f"[EMAIL] Failed to send '{subject}' to {to_email}: {error_message}")

        # Log to database
        self._log_email(to_email, subject, email_type, success, error_message, related_request_id)

        return success

    def _log_email(self, recipient_email: str, subject: str, email_type: str,
                  success: bool, error_message: Optional[str],
                  related_request_id: Optional[int]):
        """Log email attempt to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now().isoformat()

        cursor.execute('''
            INSERT INTO email_log (recipient_email, subject, email_type, sent_at,
                                 success, error_message, related_request_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (recipient_email, subject, email_type, now, int(success),
              error_message, related_request_id))

        conn.commit()
        conn.close()

    # ==================== Email Templates ====================

    def send_access_request_email(self, admin_email: str, username: str,
                                  full_name: str, email: str, reason: str,
                                  request_id: int) -> bool:
        """
        Send email to admin about new access request

        Args:
            admin_email: Admin email address
            username: Requested username
            full_name: User's full name
            email: User's email
            reason: Reason for access
            request_id: Access request ID

        Returns:
            True if successful
        """
        subject = f"New Access Request - {username}"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                          color: white; padding: 20px; border-radius: 5px 5px 0 0; }}
                .content {{ background: #f9f9f9; padding: 20px; border-radius: 0 0 5px 5px; }}
                .info {{ background: white; padding: 15px; margin: 10px 0; border-left: 4px solid #667eea; }}
                .button {{ display: inline-block; padding: 10px 20px; background: #667eea;
                          color: white; text-decoration: none; border-radius: 5px; margin: 10px 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>🔔 New Access Request</h2>
                </div>
                <div class="content">
                    <p>A new user has requested access to Kármán:</p>

                    <div class="info">
                        <strong>Username:</strong> {username}<br>
                        <strong>Full Name:</strong> {full_name}<br>
                        <strong>Email:</strong> {email}<br>
                        <strong>Request ID:</strong> #{request_id}
                    </div>

                    <div class="info">
                        <strong>Reason for Access:</strong><br>
                        {reason}
                    </div>

                    <p>Please review and approve/reject this request in the Kármán dashboard.</p>

                    <p style="text-align: center;">
                        <a href="http://localhost:5000/admin/access-requests" class="button">
                            Review Request
                        </a>
                    </p>

                    <p style="color: #666; font-size: 12px; margin-top: 20px;">
                        This is an automated message from Kármán. Please do not reply to this email.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        return self.send_email(admin_email, subject, html_body, 'access_request', request_id)

    def send_approval_email(self, user_email: str, username: str, full_name: str) -> bool:
        """
        Send email to user about approved access request

        Args:
            user_email: User's email address
            username: Username
            full_name: User's full name

        Returns:
            True if successful
        """
        subject = "Access Approved - Welcome to Kármán"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
                          color: white; padding: 20px; border-radius: 5px 5px 0 0; }}
                .content {{ background: #f9f9f9; padding: 20px; border-radius: 0 0 5px 5px; }}
                .info {{ background: white; padding: 15px; margin: 10px 0; border-left: 4px solid #28a745; }}
                .button {{ display: inline-block; padding: 10px 20px; background: #28a745;
                          color: white; text-decoration: none; border-radius: 5px; margin: 10px 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>✅ Access Approved!</h2>
                </div>
                <div class="content">
                    <p>Hi {full_name},</p>

                    <p>Great news! Your access request for Kármán has been approved.</p>

                    <div class="info">
                        <strong>Username:</strong> {username}<br>
                        <strong>Status:</strong> Active
                    </div>

                    <p>You can now log in to Kármán and start managing your Arista devices.</p>

                    <p style="text-align: center;">
                        <a href="http://localhost:5000/login" class="button">
                            Log In Now
                        </a>
                    </p>

                    <p><strong>What's Next?</strong></p>
                    <ul>
                        <li>Log in with your username and password</li>
                        <li>Explore the device inventory</li>
                        <li>Browse configlets and CLI commands</li>
                        <li>Create and manage configuration tasks</li>
                    </ul>

                    <p>If you have any questions, please contact your administrator.</p>

                    <p style="color: #666; font-size: 12px; margin-top: 20px;">
                        This is an automated message from Kármán. Please do not reply to this email.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        return self.send_email(user_email, subject, html_body, 'approval')

    def send_rejection_email(self, user_email: str, username: str, full_name: str,
                           reason: str) -> bool:
        """
        Send email to user about rejected access request

        Args:
            user_email: User's email address
            username: Requested username
            full_name: User's full name
            reason: Reason for rejection

        Returns:
            True if successful
        """
        subject = "Access Request Update - Kármán"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
                          color: white; padding: 20px; border-radius: 5px 5px 0 0; }}
                .content {{ background: #f9f9f9; padding: 20px; border-radius: 0 0 5px 5px; }}
                .info {{ background: white; padding: 15px; margin: 10px 0; border-left: 4px solid #dc3545; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Access Request Update</h2>
                </div>
                <div class="content">
                    <p>Hi {full_name},</p>

                    <p>Thank you for your interest in Kármán. After reviewing your access request,
                    we are unable to approve it at this time.</p>

                    <div class="info">
                        <strong>Username:</strong> {username}<br>
                        <strong>Status:</strong> Not Approved
                    </div>

                    <div class="info">
                        <strong>Reason:</strong><br>
                        {reason}
                    </div>

                    <p>If you believe this is an error or would like to discuss further,
                    please contact your administrator.</p>

                    <p style="color: #666; font-size: 12px; margin-top: 20px;">
                        This is an automated message from Kármán. Please do not reply to this email.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        return self.send_email(user_email, subject, html_body, 'rejection')
