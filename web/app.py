#!/usr/bin/env python3
"""
Kármán Web Application
Production-ready Flask dashboard for Arista device orchestration
"""

import sys
import os
import sqlite3
import re
import time
import threading
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, session
from flask import send_from_directory, send_file
from functools import wraps
from datetime import datetime, timedelta
import secrets

from core.inventory import InventoryManager, Device, DeviceType, DeviceRole
from core.configlet import ConfigletManager, Configlet
from core.task import TaskManager, TaskType, TaskStatus
from core.cli_browser import CLIBrowserManager
from core.mib_browser import MIBBrowserManager
from core.cli_navigator import CLINavigator
from core.user import UserManager
from core.notification import NotificationManager
from builder import ConfigletBuilder
from validator import ConfigValidator
from web.email_sender import EmailSender
from web.auth_decorators import login_required, admin_required
from connectors.eapi_connector import EAPIConnector
from connectors.netmiko_connector import NetmikoConnector
from core.telemetry import DeviceTelemetry

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# Initialize managers
DB_PATH = os.environ.get('DATABASE_PATH', os.path.join(Path(__file__).parent.parent, 'custom-cvp.db'))
print(f"[INIT] Database path: {DB_PATH}")
print(f"[INIT] Database exists: {os.path.exists(DB_PATH)}")
if os.path.exists(DB_PATH):
    print(f"[INIT] Database size: {os.path.getsize(DB_PATH)} bytes")

inventory_mgr = InventoryManager(DB_PATH)
configlet_mgr = ConfigletManager(DB_PATH)
task_mgr = TaskManager(DB_PATH)
cli_browser_mgr = CLIBrowserManager(DB_PATH)
mib_browser_mgr = MIBBrowserManager()
cli_navigator = CLINavigator(DB_PATH)
user_mgr = UserManager(DB_PATH)
notification_mgr = NotificationManager(DB_PATH)
email_sender = EmailSender(DB_PATH)
builder = ConfigletBuilder()
validator = ConfigValidator()

# Verify configlets loaded
initial_configlet_count = len(configlet_mgr.list_configlets())
print(f"[INIT] Loaded {initial_configlet_count} configlets from database")

# ── Background telemetry cache ────────────────────────────────────────────────
# Shared via SQLite so all gunicorn workers read/write the same data.
# Only one worker polls at a time (stale-check prevents duplicate polls).
def _ensure_telemetry_cache_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS telemetry_cache (
            id       INTEGER PRIMARY KEY CHECK (id = 1),
            devices_json TEXT NOT NULL,
            updated_at   REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()

_ensure_telemetry_cache_table()

def _collect_device_telemetry(device_info, username, password):
    """Collect telemetry from a single device. Called from thread pool."""
    hostname, ip, mgmt_type, gnmi_port, polling_enabled = device_info
    device_data = {'hostname': hostname, 'ip': ip, 'telemetry': {'reachable': False}}

    if not polling_enabled:
        device_data['telemetry']['error'] = 'Polling disabled'
        return device_data

    if mgmt_type == 'ssh':
        try:
            connector = NetmikoConnector(ip, username, password, timeout=10)
            if connector.connect():
                device_data['telemetry'] = DeviceTelemetry.collect_from_device(connector)
                connector.disconnect()
            else:
                device_data['telemetry']['error'] = 'Connection failed'
        except Exception as e:
            device_data['telemetry']['error'] = str(e)

    elif mgmt_type == 'eapi':
        try:
            connector = EAPIConnector(ip, username, password, timeout=10)
            if connector.connect():
                device_data['telemetry'] = DeviceTelemetry.collect_from_device(connector)
            else:
                device_data['telemetry']['error'] = 'Connection failed'
        except Exception as e:
            device_data['telemetry']['error'] = str(e)

    elif mgmt_type == 'gnmi':
        try:
            from connectors.gnmi_connector import GNMIConnector
            port = int(gnmi_port) if gnmi_port else 6030
            connector = GNMIConnector(ip, port=port, username=username, password=password, timeout=10)
            device_data['telemetry'] = DeviceTelemetry.collect_from_gnmi(connector)
        except Exception as e:
            device_data['telemetry']['error'] = str(e)

    return device_data

def _collect_all_telemetry(username, password):
    """Collect telemetry from all devices concurrently. Returns list of device dicts."""
    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT hostname, ip_address, management_type, gnmi_port, polling_enabled FROM devices")
    devices = cursor.fetchall()
    conn.close()

    if not devices:
        return []

    telemetry_data = []
    executor = ThreadPoolExecutor(max_workers=10)
    try:
        futures = {executor.submit(_collect_device_telemetry, d, username, password): d for d in devices}
        try:
            for future in as_completed(futures, timeout=60):
                try:
                    telemetry_data.append(future.result())
                except Exception as e:
                    device = futures[future]
                    telemetry_data.append({
                        'hostname': device[0], 'ip': device[1],
                        'telemetry': {'reachable': False, 'error': str(e)}
                    })
        except FuturesTimeoutError:
            for future, device in futures.items():
                if not future.done():
                    telemetry_data.append({
                        'hostname': device[0], 'ip': device[1],
                        'telemetry': {'reachable': False, 'error': 'Collection timeout'}
                    })
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return telemetry_data

def _write_telemetry_cache(devices):
    """Write collected telemetry to the SQLite cache table."""
    import json as _json
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO telemetry_cache (id, devices_json, updated_at) VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET devices_json=excluded.devices_json, updated_at=excluded.updated_at
        """, (_json.dumps(devices), time.time()))
        conn.commit()
        conn.close()
    except Exception as e:
        app.logger.error(f"[Cache] Write error: {e}")

def _background_telemetry_loop():
    """Daemon thread: keeps telemetry cache warm. Only polls when cache is stale.

    Uses a DB-level lock (app_settings row 'telemetry_lock_at') to prevent
    multiple gunicorn workers from polling simultaneously.  The lock is valid
    for 90 s — long enough to cover a full collection cycle.
    """
    # Stagger startup by pid so workers don't all race at exactly t=15s
    time.sleep(15 + (os.getpid() % 10))
    while True:
        try:
            now = time.time()
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            # Read cache age and lock timestamp in one connection
            cursor.execute("SELECT updated_at FROM telemetry_cache WHERE id=1")
            row = cursor.fetchone()
            cache_age = now - row[0] if row else 999

            cursor.execute("SELECT value FROM app_settings WHERE key='telemetry_lock_at'")
            lock_row = cursor.fetchone()
            lock_age = now - float(lock_row[0]) if lock_row else 999

            should_collect = cache_age >= 28 and lock_age >= 90

            if should_collect:
                # Claim the lock before releasing the connection
                cursor.execute(
                    "INSERT INTO app_settings(key, value) VALUES('telemetry_lock_at', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(now),)
                )
                conn.commit()
            conn.close()

            if should_collect:
                username = os.environ.get('DEFAULT_DEVICE_USERNAME', 'admin')
                password = os.environ.get('DEFAULT_DEVICE_PASSWORD', '')
                result = _collect_all_telemetry(username, password)
                if result:
                    _write_telemetry_cache(result)
                    app.logger.info(f"[BG] Telemetry cache refreshed ({len(result)} devices)")
        except Exception as e:
            app.logger.error(f"[BG] Telemetry loop error: {e}")
        time.sleep(15)  # Check every 15 s; poll only when stale

_bg_telemetry_thread = threading.Thread(
    target=_background_telemetry_loop, daemon=True, name='telemetry-bg'
)
_bg_telemetry_thread.start()
print("[INIT] Background telemetry thread started")

# Check if first user setup is needed
first_user = user_mgr.is_first_user()
print(f"[INIT] First user setup needed: {first_user}")

# Template filters
@app.template_filter('datetime')
def format_datetime(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except:
            return value
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return value

@app.template_filter('timeago')
def timeago(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except:
            return value
    if isinstance(value, datetime):
        now = datetime.now()
        diff = now - value
        if diff.days > 0:
            return f"{diff.days} days ago"
        elif diff.seconds > 3600:
            return f"{diff.seconds // 3600} hours ago"
        elif diff.seconds > 60:
            return f"{diff.seconds // 60} minutes ago"
        else:
            return "just now"
    return value

@app.template_filter('number_format')
def number_format(value):
    """Format number with thousands separator"""
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return value

# Context processor for global variables
@app.context_processor
def inject_globals():
    pending_count = 0
    if session.get('is_admin'):
        pending_count = notification_mgr.get_pending_requests_count()

    return {
        'app_name': 'Kármán',
        'app_version': '1.0.0',
        'current_user': session.get('username', 'Guest'),
        'pending_request_count': pending_count
    }

# ==================== Authentication Routes ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            password = request.form.get('password')

            if not username or not password:
                flash('Please enter both username and password', 'danger')
                return render_template('login.html')

            # Check if account is locked
            try:
                if user_mgr.is_account_locked(username):
                    flash('Account is locked due to too many failed login attempts. Please try again later.', 'danger')
                    try:
                        user_mgr.log_auth_event('login_attempt_locked', username, request.remote_addr, {}, success=False)
                    except:
                        pass  # Log failure is non-critical
                    return render_template('login.html')
            except:
                pass  # If we can't check locked status, continue with login

            # Verify credentials
            user = user_mgr.verify_credentials(username, password)

            if user and user['is_active']:
                # Successful login
                try:
                    user_mgr.reset_failed_attempts(username)
                    user_mgr.update_last_login(user['user_id'])
                except:
                    pass  # Non-critical if these fail

                # Clear old session and create new one (prevent session fixation)
                session.clear()
                session['logged_in'] = True
                session['user_id'] = user['user_id']
                session['username'] = user['username']
                session['is_admin'] = user['is_admin']
                session.permanent = True

                # Log successful login
                try:
                    user_mgr.log_auth_event('login_success', username, request.remote_addr, {}, success=True)
                except:
                    pass  # Log failure is non-critical

                flash(f'Welcome back, {username}!', 'success')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('dashboard'))
            else:
                # Failed login
                try:
                    if user_mgr.get_user_by_username(username):
                        # User exists but wrong password or inactive
                        user_mgr.increment_failed_login(username)
                    user_mgr.log_auth_event('login_failed', username, request.remote_addr, {}, success=False)
                except:
                    pass  # Log failure is non-critical

                flash('Invalid credentials or account not activated', 'danger')

        except Exception as e:
            app.logger.error(f"Login error: {str(e)}")
            flash('An error occurred during login. Please check database permissions.', 'danger')

    return render_template('login.html')

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    username = session.get('username', 'unknown')
    try:
        user_mgr.log_auth_event('logout', username, request.remote_addr, {})
    except Exception:
        pass
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            full_name = request.form.get('full_name', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            reason = ''

            # Validate password match
            if password != confirm_password:
                flash('Passwords do not match', 'danger')
                return render_template('register.html')

            # Check if this is the first user
            if user_mgr.is_first_user():
                # First user becomes admin immediately
                user_id = user_mgr.create_user_direct(username, email, full_name, password, is_admin=True)
                flash(f'Welcome! You are the first user and have been granted administrator access.', 'success')
                return redirect(url_for('login'))
            else:
                # Create access request
                request_id = user_mgr.create_access_request(username, email, full_name, password, reason)

                # Get admin user to notify
                admin_users = [u for u in user_mgr.list_all_users() if u.is_admin]
                if admin_users:
                    admin_user = admin_users[0]  # Notify first admin
                    notification_mgr.notify_new_access_request(admin_user.user_id, username, request_id)

                    # Send email notification
                    email_sender.send_access_request_email(
                        admin_user.email, username, full_name, email, reason, request_id
                    )

                flash('Access request submitted successfully. Please wait for admin approval.', 'success')
                return redirect(url_for('access_pending'))

        except ValueError as e:
            flash(str(e), 'danger')
        except Exception as e:
            flash(f'Error creating access request: {str(e)}', 'danger')

    return render_template('register.html')

@app.route('/access-pending')
def access_pending():
    return render_template('access_pending.html')

@app.route('/settings')
@login_required
def settings():
    """User settings page"""
    user = user_mgr.get_user_by_username(session['username'])
    email_settings = email_sender.get_email_settings() if user.is_admin else None
    return render_template('settings.html', user=user, email_settings=email_settings)

@app.route('/admin/settings/email', methods=['POST'])
@login_required
@admin_required
def admin_settings_email():
    """Save email/SMTP settings"""
    # Checkboxes are absent from POST when unchecked, so default to 'false'
    email_sender.set_setting('email_enabled', 'true' if request.form.get('email_enabled') else 'false')
    email_sender.set_setting('smtp_use_tls',  'true' if request.form.get('smtp_use_tls')  else 'false')
    for key in ['smtp_host', 'smtp_port', 'smtp_username', 'from_email']:
        email_sender.set_setting(key, request.form.get(key, ''))
    # Only overwrite password if a new one was supplied
    new_password = request.form.get('smtp_password', '')
    if new_password:
        email_sender.set_setting('smtp_password', new_password)
    flash('Email settings saved.', 'success')
    return redirect(url_for('settings'))

@app.route('/admin/access-requests')
@login_required
@admin_required
def access_requests():
    requests = user_mgr.list_pending_requests()
    return render_template('admin/access_requests.html', requests=requests)

@app.route('/admin/access-requests/<int:request_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_request(request_id):
    try:
        # Get request details before approval
        access_request = user_mgr.get_access_request(request_id)
        if not access_request:
            flash('Access request not found', 'danger')
            return redirect(url_for('access_requests'))

        # Approve the request
        user_id = user_mgr.approve_request(request_id, session['username'])

        # Create notification for new user
        notification_mgr.notify_request_approved(user_id, session['username'])

        # Send approval email
        email_sender.send_approval_email(
            access_request.email, access_request.username, access_request.full_name
        )

        flash(f'Access approved for {access_request.username}', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception as e:
        flash(f'Error approving request: {str(e)}', 'danger')

    return redirect(url_for('access_requests'))

@app.route('/admin/access-requests/<int:request_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_request(request_id):
    try:
        reason = request.form.get('reason', 'No reason provided')

        # Get request details before rejection
        access_request = user_mgr.get_access_request(request_id)
        if not access_request:
            flash('Access request not found', 'danger')
            return redirect(url_for('access_requests'))

        # Reject the request
        user_mgr.reject_request(request_id, session['username'], reason)

        # Send rejection email
        email_sender.send_rejection_email(
            access_request.email, access_request.username, access_request.full_name, reason
        )

        flash(f'Access rejected for {access_request.username}', 'info')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception as e:
        flash(f'Error rejecting request: {str(e)}', 'danger')

    return redirect(url_for('access_requests'))

# ==================== Notification API Routes ====================

@app.route('/api/notifications/unread-count')
@login_required
def api_notification_count():
    """Get unread notification count for current user"""
    count = notification_mgr.get_unread_count(session['user_id'])
    return jsonify({'count': count})

@app.route('/api/notifications')
@login_required
def api_notifications():
    """Get recent notifications for current user"""
    notifications = notification_mgr.get_user_notifications(session['user_id'], limit=20)
    return jsonify([n.to_dict() for n in notifications])

@app.route('/api/notifications/<int:notification_id>/mark-read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark notification as read"""
    success = notification_mgr.mark_as_read(notification_id)
    return jsonify({'success': success})

@app.route('/api/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read for current user"""
    count = notification_mgr.mark_all_as_read(session['user_id'])
    return jsonify({'marked': count})

# ==================== Health Check ====================

@app.route('/health')
def health():
    """Health check endpoint for container orchestration"""
    try:
        # Check database connectivity
        db_ok = os.path.exists(DB_PATH)

        # Check if we can query the database
        if db_ok:
            try:
                configlets = configlet_mgr.list_configlets()
                db_ok = True
            except:
                db_ok = False

        status = "healthy" if db_ok else "unhealthy"
        status_code = 200 if db_ok else 503

        return jsonify({
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "database": "connected" if db_ok else "error",
            "version": "1.0.0"
        }), status_code
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 503

# ==================== Dashboard ====================

@app.route('/')
@login_required
def dashboard():
    # Get statistics
    devices = inventory_mgr.list_all_devices()
    total_devices = len(devices)

    cvp_managed = len([d for d in devices if inventory_mgr.get_device(d).cvp_managed])
    custom_managed = total_devices - cvp_managed

    configlets = configlet_mgr.list_configlets()
    total_configlets = len(configlets)

    tasks = task_mgr.list_tasks()
    pending_tasks = len([t for t in tasks if t['status'] == 'pending'])

    # Recent activity
    recent_tasks = task_mgr.list_tasks()[:5]

    # Device breakdown by role + inventory list for immediate card rendering
    device_roles = {}
    device_list = []
    for hostname in devices:
        device = inventory_mgr.get_device(hostname)
        role = device.role.value
        device_roles[role] = device_roles.get(role, 0) + 1
        device_list.append({
            'hostname': device.hostname,
            'ip': device.ip_address,
            'model': device.model or '',
            'eos_version': device.eos_version or '',
            'site': device.site or '',
            'role': role,
            'management_type': device.management_type.value,
        })

    return render_template('dashboard.html',
                         total_devices=total_devices,
                         cvp_managed=cvp_managed,
                         custom_managed=custom_managed,
                         total_configlets=total_configlets,
                         pending_tasks=pending_tasks,
                         recent_tasks=recent_tasks,
                         device_roles=device_roles,
                         device_list=device_list)

# ==================== Device Routes ====================

@app.route('/devices')
@login_required
def devices():
    devices = []
    for hostname in inventory_mgr.list_all_devices():
        device = inventory_mgr.get_device(hostname)
        devices.append(device)

    # Apply filters
    role_filter = request.args.get('role')
    site_filter = request.args.get('site')
    mgmt_filter = request.args.get('mgmt_type')

    if role_filter:
        devices = [d for d in devices if d.role.value == role_filter]
    if site_filter:
        devices = [d for d in devices if d.site == site_filter]
    if mgmt_filter:
        devices = [d for d in devices if d.management_type.value == mgmt_filter]

    return render_template('devices.html', devices=devices)

@app.route('/devices/<hostname>')
@login_required
def device_detail(hostname):
    device = inventory_mgr.get_device(hostname)
    if not device:
        flash(f'Device {hostname} not found', 'danger')
        return redirect(url_for('devices'))

    return render_template('device_detail.html', device=device)

@app.route('/api/devices/<hostname>/execute', methods=['POST'])
@login_required
def execute_device_command(hostname):
    """Execute a command on a device and return output"""
    try:
        device = inventory_mgr.get_device(hostname)
        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        data = request.get_json()
        command = data.get('command', '').strip()

        if not command:
            return jsonify({'success': False, 'error': 'No command provided'}), 400

        # Security: Block dangerous commands
        dangerous_patterns = [
            r'reload',
            r'write\s+erase',
            r'delete',
            r'format',
            r'upgrade',
            r'copy.*running.*startup',  # Allow read-only, block write
            r'configure\s+terminal',
            r'bash',
            r'enable\s+password'
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return jsonify({
                    'success': False,
                    'error': f'Command blocked for security: {command}'
                }), 403

        # Get credentials from request body or fall back to environment/defaults
        username = data.get('username') or os.environ.get('DEFAULT_DEVICE_USERNAME') or 'admin'
        password = data.get('password', '') or os.environ.get('DEFAULT_DEVICE_PASSWORD', '')

        # Execute command based on management type
        output = None
        if device.management_type.value == 'eapi':
            connector = EAPIConnector(device.ip_address, username, password)
            if connector.connect():
                result = connector.execute_commands([command])
                if result and len(result) > 0:
                    # Get output from result
                    data = result[0].get('result', result[0]) if isinstance(result[0], dict) else {}
                    if 'output' in data:
                        output = data['output']
                    else:
                        # Convert structured data to readable format
                        import json
                        output = json.dumps(data, indent=2)
            else:
                return jsonify({'success': False, 'error': 'Failed to connect via eAPI'}), 500

        elif device.management_type.value == 'ssh':
            connector = NetmikoConnector(device.ip_address, username, password)
            if connector.connect():
                output = connector.execute_command(command)
                connector.disconnect()
            else:
                return jsonify({'success': False, 'error': 'Failed to connect via SSH'}), 500

        elif device.management_type.value == 'gnmi':
            # gNMI is a structured telemetry transport; CLI commands are run
            # by falling back to eAPI (which is typically also enabled on
            # real Arista devices alongside TerminAttr).
            connector = EAPIConnector(device.ip_address, username, password)
            if connector.connect():
                result = connector.execute_commands([command])
                if result and len(result) > 0:
                    data = result[0].get('result', result[0]) if isinstance(result[0], dict) else {}
                    if 'output' in data:
                        output = data['output']
                    else:
                        import json
                        output = json.dumps(data, indent=2)
            else:
                return jsonify({
                    'success': False,
                    'error': (
                        'CLI commands are executed via eAPI on gNMI-managed devices. '
                        'Ensure eAPI (HTTPS port 443) is reachable on this device.'
                    )
                }), 500

        else:
            return jsonify({'success': False, 'error': 'Unsupported management type'}), 400

        if output is None:
            return jsonify({'success': False, 'error': 'No output received'}), 500

        # Log command execution
        app.logger.info(f"User {session.get('user')} executed '{command}' on {hostname}")

        return jsonify({
            'success': True,
            'command': command,
            'output': output,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        app.logger.error(f"Error executing command on {hostname}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/devices/add', methods=['GET', 'POST'])
@login_required
def add_device():
    if request.method == 'POST':
        try:
            device = Device(
                hostname=request.form['hostname'],
                ip_address=request.form['ip_address'],
                model=request.form.get('model', 'Unknown'),
                serial_number=request.form.get('serial_number', ''),
                eos_version=request.form.get('eos_version', ''),
                management_type=DeviceType(request.form['management_type']),
                role=DeviceRole(request.form['role']),
                site=request.form['site'],
                container=request.form.get('container', 'Undefined'),
                cvp_managed=request.form.get('cvp_managed') == 'on',
                gnmi_port=int(request.form.get('gnmi_port') or 6030)
            )
            inventory_mgr.add_device(device)
            flash(f'Device {device.hostname} added successfully', 'success')
            return redirect(url_for('devices'))
        except Exception as e:
            flash(f'Error adding device: {str(e)}', 'danger')

    return render_template('device_add.html')


@app.route('/api/detect-management-type', methods=['POST'])
@login_required
def api_detect_management_type():
    """
    Probe an IP address on the standard Arista management ports and suggest
    the best management type.  Uses TCP connect only — no credentials required.

    Ports probed:
      443  → eAPI (HTTPS)
      22   → SSH
      6030 → gNMI / TerminAttr (default; caller may supply a custom port)
    """
    import socket
    from concurrent.futures import ThreadPoolExecutor, as_completed

    data = request.get_json() or {}
    ip = data.get('ip', '').strip()
    gnmi_port = int(data.get('gnmi_port', 6030))

    if not ip:
        return jsonify({'success': False, 'error': 'IP address required'}), 400

    TIMEOUT = 2  # seconds per probe

    def tcp_probe(port):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(TIMEOUT)
            result = s.connect_ex((ip, port))
            s.close()
            return port, result == 0
        except Exception:
            return port, False

    probes = {443: 'eapi', 22: 'ssh', gnmi_port: 'gnmi'}

    reachable = {}
    with ThreadPoolExecutor(max_workers=len(probes)) as pool:
        futures = {pool.submit(tcp_probe, p): p for p in probes}
        for future in as_completed(futures):
            port, ok = future.result()
            reachable[probes[port]] = ok

    # Suggest best type: gNMI > eAPI > SSH
    if reachable.get('gnmi'):
        suggested = 'gnmi'
    elif reachable.get('eapi'):
        suggested = 'eapi'
    elif reachable.get('ssh'):
        suggested = 'ssh'
    else:
        suggested = None

    available = [k for k, v in reachable.items() if v]
    detail_parts = []
    if reachable.get('gnmi'):
        detail_parts.append(f'gNMI port {gnmi_port}')
    if reachable.get('eapi'):
        detail_parts.append('eAPI port 443')
    if reachable.get('ssh'):
        detail_parts.append('SSH port 22')

    return jsonify({
        'success': True,
        'ip': ip,
        'reachable': reachable,
        'available': available,
        'suggested': suggested,
        'details': ', '.join(detail_parts) if detail_parts else 'No management ports reachable',
    })


@app.route('/devices/<hostname>/edit', methods=['GET', 'POST'])
@login_required
def edit_device(hostname):
    if request.method == 'POST':
        try:
            device = Device(
                hostname=request.form['hostname'],
                ip_address=request.form['ip_address'],
                model=request.form.get('model', 'Unknown'),
                serial_number=request.form.get('serial_number', ''),
                eos_version=request.form.get('eos_version', ''),
                management_type=DeviceType(request.form['management_type']),
                role=DeviceRole(request.form['role']),
                site=request.form['site'],
                container=request.form.get('container', 'Undefined'),
                cvp_managed=request.form.get('cvp_managed') == 'on',
                gnmi_port=int(request.form.get('gnmi_port') or 6030)
            )
            success = inventory_mgr.update_device(hostname, device)
            if success:
                flash(f'Device {device.hostname} updated successfully', 'success')
                return redirect(url_for('devices'))
            else:
                flash(f'Device {hostname} not found', 'warning')
        except Exception as e:
            flash(f'Error updating device: {str(e)}', 'danger')

    # GET request - show edit form
    device = inventory_mgr.get_device(hostname)
    if not device:
        flash(f'Device {hostname} not found', 'warning')
        return redirect(url_for('devices'))

    return render_template('device_edit.html', device=device)

@app.route('/devices/<hostname>/delete', methods=['POST'])
@login_required
def delete_device(hostname):
    try:
        app.logger.info(f"Attempting to delete device: {hostname}")
        success = inventory_mgr.delete_device(hostname)
        if success:
            app.logger.info(f"Device {hostname} deleted successfully")
            flash(f'Device {hostname} deleted successfully', 'success')
            return jsonify({'success': True, 'message': f'Device {hostname} deleted'}), 200
        else:
            app.logger.warning(f'Device {hostname} not found')
            flash(f'Device {hostname} not found', 'warning')
            return jsonify({'success': False, 'error': 'Device not found'}), 404
    except Exception as e:
        app.logger.error(f'Error deleting device {hostname}: {str(e)}')
        flash(f'Error deleting device {hostname}: {str(e)}', 'danger')
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/devices/<hostname>/toggle-polling', methods=['POST'])
@login_required
def toggle_device_polling(hostname):
    """Enable or disable telemetry polling for a device."""
    device = inventory_mgr.get_device(hostname)
    if not device:
        return jsonify({'error': 'Device not found'}), 404
    device.polling_enabled = not device.polling_enabled
    inventory_mgr.update_device(hostname, device)
    state = 'enabled' if device.polling_enabled else 'disabled'
    return jsonify({'success': True, 'polling_enabled': device.polling_enabled,
                    'message': f'Polling {state} for {hostname}'})


@app.route('/devices/<hostname>/sync', methods=['POST'])
@login_required
def sync_device(hostname):
    """Sync configuration from device"""
    try:
        device = inventory_mgr.get_device(hostname)
        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        # Get credentials from request or environment
        data = request.get_json() or {}
        username = data.get('username', os.environ.get('DEVICE_USERNAME', 'admin'))
        password = data.get('password', os.environ.get('DEVICE_PASSWORD', ''))

        # Note: Empty password is allowed (default Arista switches use admin with no password)

        # Try eAPI first, fallback to SSH
        try:
            connector = EAPIConnector(
                host=device.ip_address,
                username=username,
                password=password
            )
            if connector.connect():
                config = connector.get_running_config()
                device_info = connector.get_device_info()

                # Create or update a configlet with the running config
                configlet_name = f"{hostname}-running-config"
                configlet = Configlet(
                    name=configlet_name,
                    config=config,
                    description=f"Running config synced from {hostname}",
                    configlet_type="static"
                )

                if configlet_name in configlet_mgr.list_configlets():
                    configlet_mgr.update_configlet(
                        configlet_name, config,
                        author=session.get('username', 'web'),
                        reason=f"Synced from device at {datetime.now().isoformat()}"
                    )
                else:
                    configlet_mgr.create_configlet(configlet, author=session.get('username', 'web'))

                flash(f'Configuration synced from {hostname} successfully', 'success')
                return jsonify({'success': True, 'configlet': configlet_name})
        except Exception as e:
            # Fallback to SSH
            try:
                connector = NetmikoConnector(
                    host=device.ip_address,
                    username=username,
                    password=password
                )
                if connector.connect():
                    config = connector.get_running_config()

                    configlet_name = f"{hostname}-running-config"
                    configlet = Configlet(
                        name=configlet_name,
                        config=config,
                        description=f"Running config synced from {hostname}",
                        configlet_type="static"
                    )

                    if configlet_name in configlet_mgr.list_configlets():
                        configlet_mgr.update_configlet(
                            configlet_name, config,
                            author=session.get('username', 'web'),
                            reason=f"Synced from device at {datetime.now().isoformat()}"
                        )
                    else:
                        configlet_mgr.create_configlet(configlet, author=session.get('username', 'web'))

                    connector.disconnect()
                    flash(f'Configuration synced from {hostname} successfully (via SSH)', 'success')
                    return jsonify({'success': True, 'configlet': configlet_name})
            except Exception as ssh_error:
                raise Exception(f"Both eAPI and SSH failed. eAPI: {str(e)}, SSH: {str(ssh_error)}")

    except Exception as e:
        flash(f'Error syncing device {hostname}: {str(e)}', 'danger')
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/devices/<hostname>/compliance-check', methods=['POST'])
@login_required
def compliance_check(hostname):
    """Run compliance check against device"""
    try:
        device = inventory_mgr.get_device(hostname)
        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        # Get credentials from request or environment
        data = request.get_json() or {}
        username = data.get('username', os.environ.get('DEVICE_USERNAME', 'admin'))
        password = data.get('password', os.environ.get('DEVICE_PASSWORD', ''))

        # Note: Empty password is allowed (default Arista switches use admin with no password)

        # Get running config
        try:
            connector = EAPIConnector(
                host=device.ip_address,
                username=username,
                password=password
            )
            if connector.connect():
                config = connector.get_running_config()
            else:
                raise Exception("Failed to connect via eAPI")
        except:
            connector = NetmikoConnector(
                host=device.ip_address,
                username=username,
                password=password
            )
            if connector.connect():
                config = connector.get_running_config()
                connector.disconnect()
            else:
                raise Exception("Failed to connect to device")

        # Run validation
        is_valid, errors = validator.validate_config(config)

        # Create task for compliance check
        task_id = task_mgr.create_task(
            TaskType.COMPLIANCE_CHECK,
            [hostname],
            f"Compliance check for {hostname}",
            {'config': config, 'is_valid': is_valid, 'errors': errors},
            created_by=session.get('username', 'web')
        )

        if is_valid:
            flash(f'Compliance check passed for {hostname}', 'success')
        else:
            flash(f'Compliance check found {len(errors)} issues for {hostname}', 'warning')

        return jsonify({
            'success': True,
            'is_valid': is_valid,
            'errors': errors,
            'task_id': task_id
        })

    except Exception as e:
        flash(f'Error running compliance check on {hostname}: {str(e)}', 'danger')
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/devices/<hostname>/assign-configlet', methods=['GET', 'POST'])
@login_required
def assign_configlet(hostname):
    """Assign configlet to device"""
    device = inventory_mgr.get_device(hostname)
    if not device:
        flash(f'Device {hostname} not found', 'danger')
        return redirect(url_for('devices'))

    if request.method == 'POST':
        try:
            configlet_name = request.form.get('configlet')
            if not configlet_name:
                flash('Please select a configlet', 'warning')
                return redirect(url_for('assign_configlet', hostname=hostname))

            # Create task to assign configlet
            task_id = task_mgr.create_task(
                TaskType.CONFIGLET_ASSIGN,
                [hostname],
                f"Assign configlet '{configlet_name}' to {hostname}",
                {'configlet': configlet_name},
                created_by=session.get('username', 'web')
            )

            flash(f'Task created to assign configlet "{configlet_name}" to {hostname}', 'success')
            return redirect(url_for('task_detail', task_id=task_id))

        except Exception as e:
            flash(f'Error assigning configlet: {str(e)}', 'danger')
            return redirect(url_for('assign_configlet', hostname=hostname))

    # GET - show form
    configlets = configlet_mgr.list_configlets()
    return render_template('device_assign_configlet.html', device=device, configlets=configlets)

@app.route('/devices/<hostname>/connect', methods=['GET'])
@login_required
def connect_device(hostname):
    """Open connection to device (returns connection info for terminal)"""
    try:
        device = inventory_mgr.get_device(hostname)
        if not device:
            flash(f'Device {hostname} not found', 'danger')
            return redirect(url_for('devices'))

        # Get username from environment or use default
        # Note: Password is not shown for security, stored in browser
        default_username = os.environ.get('DEVICE_USERNAME', 'admin')

        # Return connection information for client-side terminal
        connection_info = {
            'hostname': hostname,
            'ip_address': device.ip_address,
            'management_type': device.management_type.value,
            'eapi_available': True,  # Assume eAPI is available
            'ssh_available': True,
            'username': default_username
        }

        return render_template('device_connect.html', device=device, connection_info=connection_info)

    except Exception as e:
        app.logger.error(f"Error in connect_device: {str(e)}")
        flash(f'Error loading connection info: {str(e)}', 'danger')
        return redirect(url_for('devices'))

@app.route('/devices/<hostname>/test-connection', methods=['POST'])
@login_required
def test_device_connection(hostname):
    """Test connection to device"""
    try:
        device = inventory_mgr.get_device(hostname)
        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        # Get credentials from request
        data = request.get_json()
        username = data.get('username', os.environ.get('DEVICE_USERNAME', 'admin'))
        password = data.get('password', os.environ.get('DEVICE_PASSWORD', ''))

        # Note: Empty password is allowed (default Arista switches use admin with no password)

        results = {
            'hostname': hostname,
            'ip_address': device.ip_address,
            'eapi': {'available': False, 'message': ''},
            'ssh': {'available': False, 'message': ''},
            'success': False
        }

        # Test eAPI connection
        try:
            connector = EAPIConnector(
                host=device.ip_address,
                username=username,
                password=password
            )
            if connector.connect():
                device_info = connector.get_device_info()
                # Only mark as successful if we actually got device info
                if device_info and device_info.get('version'):
                    results['eapi']['available'] = True
                    results['eapi']['message'] = f"Connected! EOS version: {device_info.get('version', 'Unknown')}"
                    results['eapi']['details'] = device_info
                    results['success'] = True
                else:
                    results['eapi']['available'] = False
                    results['eapi']['message'] = "Connection created but commands failed (likely cEOS eAPI bug)"
        except Exception as e:
            results['eapi']['message'] = f"Failed: {str(e)}"

        # Test SSH connection
        try:
            connector = NetmikoConnector(
                host=device.ip_address,
                username=username,
                password=password
            )
            if connector.connect():
                output = connector.execute_command('show version | include Software')
                connector.disconnect()
                results['ssh']['available'] = True
                results['ssh']['message'] = f"Connected! {output[:100]}"
                results['success'] = True
        except Exception as e:
            results['ssh']['message'] = f"Failed: {str(e)}"

        return jsonify(results)

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== Topology Routes ====================

@app.route('/topology')
@login_required
def topology():
    """Network topology visualization"""
    return render_template('topology.html', app_name="Kármán")

@app.route('/api/topology/discover')
@login_required
def api_topology_discover():
    """Discover network topology via LLDP"""
    try:
        from core.topology import TopologyDiscovery

        # Get credentials from query params or environment
        username = request.args.get('username') or os.environ.get('DEFAULT_DEVICE_USERNAME', 'admin')
        password = request.args.get('password', os.environ.get('DEFAULT_DEVICE_PASSWORD', ''))

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT hostname, ip_address, management_type, model, role FROM devices")

        devices_info = []
        for row in cursor.fetchall():
            hostname, ip, mgmt_type, model, role = row

            try:
                # Create appropriate connector
                lldp_fallback = None
                if mgmt_type == 'eapi':
                    connector = EAPIConnector(ip, username, password)
                    is_eapi = True
                    is_gnmi = False
                elif mgmt_type == 'ssh':
                    connector = NetmikoConnector(ip, username, password)
                    is_eapi = False
                    is_gnmi = False
                elif mgmt_type == 'gnmi':
                    from connectors.gnmi_connector import GNMIConnector
                    cursor2 = conn.cursor()
                    cursor2.execute(
                        "SELECT gnmi_port FROM devices WHERE hostname = ?", (hostname,)
                    )
                    port_row = cursor2.fetchone()
                    gnmi_port = int(port_row[0]) if port_row and port_row[0] else 6030
                    connector = GNMIConnector(ip, port=gnmi_port,
                                             username=username, password=password,
                                             timeout=10)
                    is_eapi = False
                    is_gnmi = True
                    # SSH fallback for LLDP — used when gNMI returns no OC LLDP data
                    lldp_fallback = NetmikoConnector(ip, username, password)
                else:
                    # CVP-managed devices — topology is owned by CVP
                    continue

                # For eAPI and SSH, connect now; gNMI connects per-query in topology.py
                if not is_gnmi:
                    if not connector.connect():
                        continue

                devices_info.append({
                    'hostname': hostname,
                    'connector': connector,
                    'is_eapi': is_eapi,
                    'is_gnmi': is_gnmi,
                    'role': role or 'unknown',
                    'model': model or 'unknown',
                    'ip': ip,
                    'management_type': mgmt_type,
                    'lldp_fallback': lldp_fallback,
                })

            except Exception as e:
                app.logger.error(f"Failed to connect to {hostname}: {e}")
                continue

        # Discover topology
        topology = TopologyDiscovery.discover_topology(devices_info)
        stats = TopologyDiscovery.get_topology_stats(topology)

        # Disconnect all connectors
        for device_info in devices_info:
            try:
                if hasattr(device_info['connector'], 'disconnect'):
                    device_info['connector'].disconnect()
            except:
                pass
            try:
                fb = device_info.get('lldp_fallback')
                if fb and hasattr(fb, 'disconnect'):
                    fb.disconnect()
            except:
                pass

        conn.close()

        return jsonify({
            'success': True,
            'topology': topology,
            'stats': stats,
            'device_status': topology.get('device_status', []),
        })

    except Exception as e:
        app.logger.error(f"Topology discovery error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== Configlet Routes ====================

@app.route('/configlets/simple')
@login_required
def simple_configlets():
    """Simplified configlets view without Bootstrap - for troubleshooting"""
    try:
        configlet_names = configlet_mgr.list_configlets()
        configlets_list = []

        for name in configlet_names:
            cfg = configlet_mgr.get_configlet(name)
            if cfg:
                configlets_list.append({
                    'name': cfg.name,
                    'type': cfg.configlet_type,
                    'description': cfg.description,
                    'lines': len(cfg.config.split('\n'))
                })

        search = request.args.get('search', '')
        if search:
            configlets_list = [c for c in configlets_list if search.lower() in c['name'].lower()]

        return render_template('configlets_simple.html', configlets=configlets_list, search=search)
    except Exception as e:
        return render_template('configlets_simple.html', configlets=[], search='', error=str(e))

@app.route('/configlets/debug')
@login_required
def debug_configlets():
    """Debug page to troubleshoot configlet display issues"""
    try:
        configlet_names = configlet_mgr.list_configlets()
        configlets_list = []

        for name in configlet_names:
            cfg = configlet_mgr.get_configlet(name)
            if cfg:
                configlets_list.append({
                    'name': cfg.name,
                    'type': cfg.configlet_type,
                    'description': cfg.description,
                    'lines': len(cfg.config.split('\n'))
                })

        search = request.args.get('search', '')
        if search:
            configlets_list = [c for c in configlets_list if search.lower() in c['name'].lower()]

        return render_template('debug_configlets.html', configlets=configlets_list, search=search)
    except Exception as e:
        return render_template('debug_configlets.html', configlets=[], search='', error=str(e))

@app.route('/configlets')
@login_required
def configlets():
    try:
        configlet_names = configlet_mgr.list_configlets()
        configlets_list = []

        for name in configlet_names:
            cfg = configlet_mgr.get_configlet(name)
            if cfg:
                configlets_list.append({
                    'name': cfg.name,
                    'type': cfg.configlet_type,
                    'description': cfg.description,
                    'lines': len(cfg.config.split('\n'))
                })

        # Apply filters
        search = request.args.get('search', '')
        filter_type = request.args.get('filter_type', '')
        filter_group = request.args.get('filter_group', '')

        if search:
            configlets_list = [c for c in configlets_list if search.lower() in c['name'].lower() or search.lower() in c.get('description', '').lower()]

        if filter_type:
            configlets_list = [c for c in configlets_list if c.get('type') == filter_type]

        # Smart grouping: detect naming patterns
        from collections import defaultdict
        import re

        def get_group_name(name):
            """Extract group name from configlet name using custom pattern"""
            separator = session.get('groupSeparator', '-')
            custom_pattern = session.get('customPattern', '')

            if separator == 'custom' and custom_pattern:
                try:
                    match = re.match(custom_pattern, name)
                    return match.group(1) if match and len(match.groups()) > 0 else 'Other'
                except:
                    return 'Other'
            elif separator in name:
                return name.split(separator)[0]
            else:
                return 'Other'

        # Get grouping preference from query param
        group_by = request.args.get('group_by', 'name')  # 'name', 'type', or 'none'

        grouped_configlets = defaultdict(list)

        if group_by == 'name':
            # Group by naming pattern
            for cfg in configlets_list:
                group = get_group_name(cfg['name'])
                grouped_configlets[group].append(cfg)
        elif group_by == 'type':
            # Group by type
            for cfg in configlets_list:
                grouped_configlets[cfg['type']].append(cfg)
        else:
            # No grouping - all in one group
            grouped_configlets['All Configlets'] = configlets_list

        # Apply group filter if specified
        if filter_group and group_by != 'none':
            configlets_list = [c for c in configlets_list if get_group_name(c['name']) == filter_group]

        # Re-group after filtering
        grouped_configlets = defaultdict(list)
        if group_by == 'name':
            for cfg in configlets_list:
                group = get_group_name(cfg['name'])
                grouped_configlets[group].append(cfg)
        elif group_by == 'type':
            for cfg in configlets_list:
                grouped_configlets[cfg['type']].append(cfg)
        else:
            grouped_configlets['All Configlets'] = configlets_list

        # Sort within each group
        for group_name in grouped_configlets:
            grouped_configlets[group_name].sort(key=lambda x: x['name'])

        # Get all unique groups for filter dropdown
        all_groups = sorted(set(get_group_name(c['name']) for c in configlets_list))

        return render_template('configlets.html',
                             configlets=configlets_list,
                             grouped_configlets=dict(grouped_configlets),
                             search=search,
                             group_by=group_by,
                             all_groups=all_groups)
    except Exception as e:
        app.logger.error(f"Error in configlets route: {str(e)}")
        flash(f"Error loading configlets: {str(e)}", "danger")
        return render_template('configlets.html', configlets=[], grouped_configlets={}, search='')

@app.route('/configlets/<name>')
@login_required
def configlet_detail(name):
    configlet = configlet_mgr.get_configlet(name)
    if not configlet:
        flash(f'Configlet {name} not found', 'danger')
        return redirect(url_for('configlets'))

    history = configlet_mgr.get_configlet_history(name)

    return render_template('configlet_detail.html', configlet=configlet, history=history)

@app.route('/configlets/create', methods=['GET', 'POST'])
@login_required
def create_configlet():
    if request.method == 'POST':
        try:
            name = request.form['name']
            config = request.form['config']
            description = request.form.get('description', '')
            configlet_type = request.form.get('type', 'static')

            configlet = Configlet(name, config, description, configlet_type)
            configlet_mgr.create_configlet(configlet, author=session.get('username', 'web'))

            flash(f'Configlet {name} created successfully', 'success')
            return redirect(url_for('configlet_detail', name=name))
        except Exception as e:
            flash(f'Error creating configlet: {str(e)}', 'danger')

    return render_template('configlet_create.html')

@app.route('/configlets/<name>/edit', methods=['GET', 'POST'])
@login_required
def edit_configlet(name):
    configlet = configlet_mgr.get_configlet(name)
    if not configlet:
        flash(f'Configlet {name} not found', 'danger')
        return redirect(url_for('configlets'))

    if request.method == 'POST':
        try:
            new_config = request.form['config']
            reason = request.form.get('reason', 'Updated via web interface')

            configlet_mgr.update_configlet(
                name, new_config,
                author=session.get('username', 'web'),
                reason=reason
            )
            flash(f'Configlet {name} updated successfully', 'success')
            return redirect(url_for('configlet_detail', name=name))
        except Exception as e:
            flash(f'Error updating configlet: {str(e)}', 'danger')

    return render_template('configlet_edit.html', configlet=configlet)

@app.route('/configlets/<name>/delete', methods=['POST'])
@login_required
def delete_configlet(name):
    """Delete a configlet"""
    try:
        configlet = configlet_mgr.get_configlet(name)
        if not configlet:
            flash(f'Configlet {name} not found', 'warning')
            return redirect(url_for('configlets'))

        # Delete the configlet
        success = configlet_mgr.delete_configlet(name)
        if success:
            flash(f'Configlet {name} deleted successfully', 'success')
        else:
            flash(f'Failed to delete configlet {name}', 'danger')

    except Exception as e:
        flash(f'Error deleting configlet {name}: {str(e)}', 'danger')

    return redirect(url_for('configlets'))

@app.route('/configlets/<name>/export')
@login_required
def export_configlet(name):
    """Export configlet as downloadable file"""
    try:
        configlet = configlet_mgr.get_configlet(name)
        if not configlet:
            flash(f'Configlet {name} not found', 'danger')
            return redirect(url_for('configlets'))

        # Create response with configlet content
        from flask import make_response
        response = make_response(configlet.config)
        response.headers['Content-Type'] = 'text/plain'
        response.headers['Content-Disposition'] = f'attachment; filename={name}.cfg'
        return response

    except Exception as e:
        flash(f'Error exporting configlet {name}: {str(e)}', 'danger')
        return redirect(url_for('configlet_detail', name=name))

# ==================== Configuration Builder Routes ====================

@app.route('/builder')
@login_required
def config_builder():
    # List available templates
    template_dir = Path(__file__).parent.parent / 'templates'
    templates = []

    for category in ['base', 'layer2', 'layer3', 'overlays']:
        cat_dir = template_dir / category
        if cat_dir.exists():
            for template_file in cat_dir.glob('*.j2'):
                templates.append({
                    'category': category,
                    'name': template_file.name,
                    'path': f'{category}/{template_file.name}'
                })

    # List available device vars
    var_dir = Path(__file__).parent.parent / 'variables' / 'device-vars'
    device_vars = []
    if var_dir.exists():
        device_vars = [f.name for f in var_dir.glob('*.yaml')]

    return render_template('builder.html', templates=templates, device_vars=device_vars)

@app.route('/builder/build', methods=['POST'])
@login_required
def build_config():
    try:
        device_file = request.form['device_file']
        selected_templates = request.form.getlist('templates')
        output_name = request.form.get('output_name', 'generated.cfg')

        if not selected_templates:
            flash('Please select at least one template', 'warning')
            return redirect(url_for('config_builder'))

        # Build configuration
        output_path = builder.build_configlet(device_file, selected_templates, output_name)

        # Read generated config
        with open(output_path, 'r') as f:
            generated_config = f.read()

        flash(f'Configuration built successfully: {output_name}', 'success')
        return render_template('builder_result.html',
                             config=generated_config,
                             filename=output_name,
                             device=device_file)
    except Exception as e:
        flash(f'Error building configuration: {str(e)}', 'danger')
        return redirect(url_for('config_builder'))

@app.route('/builder/validate', methods=['POST'])
@login_required
def validate_builder_config():
    """Validate generated configuration"""
    try:
        data = request.get_json()
        config = data.get('config', '')

        if not config:
            return jsonify({'success': False, 'error': 'No configuration provided'}), 400

        # Validate configuration
        is_valid, errors = validator.validate_config(config)

        return jsonify({
            'success': True,
            'is_valid': is_valid,
            'errors': errors,
            'error_count': len(errors)
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/builder/deploy', methods=['POST'])
@login_required
def deploy_builder_config():
    """Deploy generated configuration to device"""
    try:
        data = request.get_json()
        config = data.get('config', '')
        device = data.get('device', '')
        filename = data.get('filename', 'generated.cfg')

        if not config:
            return jsonify({'success': False, 'error': 'No configuration provided'}), 400

        if not device:
            return jsonify({'success': False, 'error': 'No device specified'}), 400

        # Extract hostname from device file (e.g., "leaf1-dc1.yaml" -> "leaf1-dc1")
        hostname = device.replace('.yaml', '').replace('.yml', '')

        # Create a configlet from the generated config
        configlet_name = f"builder-{filename.replace('.cfg', '')}"
        configlet = Configlet(
            name=configlet_name,
            config=config,
            description=f"Generated configuration from builder for {hostname}",
            configlet_type="builder"
        )

        # Create or update configlet
        if configlet_name in configlet_mgr.list_configlets():
            configlet_mgr.update_configlet(
                configlet_name, config,
                author=session.get('username', 'web'),
                reason=f"Updated via builder deployment"
            )
        else:
            configlet_mgr.create_configlet(configlet, author=session.get('username', 'web'))

        # Create deployment task
        task_id = task_mgr.create_task(
            TaskType.CONFIGLET_DEPLOY,
            [hostname],
            f"Deploy builder configuration '{configlet_name}' to {hostname}",
            {'configlet': configlet_name, 'config': config},
            created_by=session.get('username', 'web')
        )

        return jsonify({
            'success': True,
            'task_id': task_id,
            'configlet': configlet_name,
            'message': f'Deployment task created for {hostname}'
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/builder/create-task', methods=['POST'])
@login_required
def create_builder_task():
    """Create task from builder configuration"""
    try:
        data = request.get_json()
        config = data.get('config', '')
        device = data.get('device', '')
        filename = data.get('filename', 'generated.cfg')

        if not config or not device:
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

        # Extract hostname
        hostname = device.replace('.yaml', '').replace('.yml', '')

        # Create configlet first
        configlet_name = f"builder-{filename.replace('.cfg', '')}"
        configlet = Configlet(
            name=configlet_name,
            config=config,
            description=f"Generated configuration from builder",
            configlet_type="builder"
        )

        if configlet_name not in configlet_mgr.list_configlets():
            configlet_mgr.create_configlet(configlet, author=session.get('username', 'web'))

        # Create task
        task_id = task_mgr.create_task(
            TaskType.CONFIG_BUILD,
            [hostname],
            f"Apply builder configuration '{configlet_name}'",
            {'configlet': configlet_name, 'source': 'builder'},
            created_by=session.get('username', 'web')
        )

        return jsonify({
            'success': True,
            'task_id': task_id,
            'configlet': configlet_name
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== Task Routes ====================

@app.route('/tasks')
@login_required
def tasks():
    status_filter = request.args.get('status')

    if status_filter:
        task_status = TaskStatus(status_filter)
        tasks_list = task_mgr.list_tasks(task_status)
    else:
        tasks_list = task_mgr.list_tasks()

    return render_template('tasks.html', tasks=tasks_list, status_filter=status_filter)

@app.route('/tasks/<int:task_id>')
@login_required
def task_detail(task_id):
    task = task_mgr.get_task(task_id)
    if not task:
        flash(f'Task {task_id} not found', 'danger')
        return redirect(url_for('tasks'))

    logs = task_mgr.get_task_logs(task_id)

    return render_template('task_detail.html', task=task, logs=logs)

@app.route('/tasks/create', methods=['GET', 'POST'])
@login_required
def create_task():
    if request.method == 'POST':
        try:
            task_type = TaskType(request.form['task_type'])
            devices = request.form['devices'].split(',')
            devices = [d.strip() for d in devices]
            description = request.form['description']

            # Get configlets if task is configlet-related
            metadata = {}
            if 'configlets' in request.form:
                metadata['configlets'] = request.form.getlist('configlets')

            task_id = task_mgr.create_task(
                task_type, devices, description, metadata,
                created_by=session.get('username', 'web')
            )

            flash(f'Task {task_id} created successfully', 'success')
            return redirect(url_for('task_detail', task_id=task_id))
        except Exception as e:
            flash(f'Error creating task: {str(e)}', 'danger')

    # Get devices and configlets for selection
    devices = inventory_mgr.list_all_devices()
    configlets = configlet_mgr.list_configlets()

    return render_template('task_create.html', devices=devices, configlets=configlets)

@app.route('/tasks/<int:task_id>/execute', methods=['POST'])
@login_required
def execute_task(task_id):
    """Execute a task"""
    try:
        task = task_mgr.get_task(task_id)
        if not task:
            flash('Task not found', 'danger')
            return redirect(url_for('tasks'))

        # Update status to in_progress
        task_mgr.update_task_status(task_id, TaskStatus.IN_PROGRESS)

        # TODO: Implement actual task execution logic based on task type
        # For now, just mark as completed
        task_mgr.update_task_status(task_id, TaskStatus.COMPLETED)

        flash(f'Task {task_id} executed successfully', 'success')
    except Exception as e:
        flash(f'Error executing task: {str(e)}', 'danger')

    return redirect(url_for('task_detail', task_id=task_id))

@app.route('/tasks/<int:task_id>/cancel', methods=['POST'])
@login_required
def cancel_task(task_id):
    """Cancel a task"""
    try:
        task_mgr.update_task_status(task_id, TaskStatus.CANCELLED)
        flash(f'Task {task_id} cancelled', 'warning')
    except Exception as e:
        flash(f'Error cancelling task: {str(e)}', 'danger')

    return redirect(url_for('task_detail', task_id=task_id))

@app.route('/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    """Delete a task and its logs"""
    try:
        if task_mgr.delete_task(task_id):
            flash(f'Task #{task_id} deleted.', 'success')
        else:
            flash('Task not found.', 'danger')
    except Exception as e:
        flash(f'Error deleting task: {str(e)}', 'danger')

    return redirect(url_for('tasks'))

@app.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    """Edit a task"""
    task = task_mgr.get_task(task_id)
    if not task:
        flash('Task not found', 'danger')
        return redirect(url_for('tasks'))

    if request.method == 'POST':
        try:
            description = request.form['description']
            devices = request.form['devices'].split(',')
            devices = [d.strip() for d in devices]

            # Update task (need to implement update_task in TaskManager)
            # For now, just flash a message
            flash(f'Task {task_id} updated successfully', 'success')
            return redirect(url_for('task_detail', task_id=task_id))
        except Exception as e:
            flash(f'Error updating task: {str(e)}', 'danger')

    devices = inventory_mgr.list_all_devices()
    configlets = configlet_mgr.list_configlets()

    return render_template('task_edit.html', task=task, devices=devices, configlets=configlets)

# ==================== API Routes ====================

@app.route('/api/stats')
@login_required
def api_stats():
    devices = inventory_mgr.list_all_devices()
    configlets = configlet_mgr.list_configlets()
    tasks = task_mgr.list_tasks()

    return jsonify({
        'devices': {
            'total': len(devices),
            'cvp_managed': len([d for d in devices if inventory_mgr.get_device(d).cvp_managed]),
            'custom_managed': len([d for d in devices if not inventory_mgr.get_device(d).cvp_managed])
        },
        'configlets': {
            'total': len(configlets)
        },
        'tasks': {
            'total': len(tasks),
            'pending': len([t for t in tasks if t['status'] == 'pending']),
            'completed': len([t for t in tasks if t['status'] == 'completed'])
        }
    })

@app.route('/api/topology')
@login_required
def api_topology():
    """Generate topology data for visualization"""
    devices = []
    links = []

    for hostname in inventory_mgr.list_all_devices():
        device = inventory_mgr.get_device(hostname)
        devices.append({
            'id': device.hostname,
            'label': device.hostname,
            'role': device.role.value,
            'site': device.site,
            'ip': device.ip_address,
            'cvp_managed': device.cvp_managed
        })

    # Note: Link discovery would require parsing configs or LLDP data
    # For now, return devices only

    return jsonify({
        'nodes': devices,
        'links': links
    })

@app.route('/api/configlets')
@login_required
def api_configlets():
    """Debug endpoint - list all configlets in JSON format"""
    try:
        configlet_names = configlet_mgr.list_configlets()
        configlets_data = []

        for name in configlet_names:
            cfg = configlet_mgr.get_configlet(name)
            if cfg:
                configlets_data.append({
                    'name': cfg.name,
                    'type': cfg.configlet_type,
                    'description': cfg.description,
                    'lines': len(cfg.config.split('\n')),
                    'hash': cfg.hash[:8]  # First 8 chars of hash
                })

        return jsonify({
            'total': len(configlets_data),
            'configlets': configlets_data
        })
    except Exception as e:
        return jsonify({
            'error': str(e),
            'total': 0,
            'configlets': []
        }), 500

# ==================== CLI Browser Routes ====================

@app.route('/cli-browser')
@login_required
def cli_browser():
    """CLI command browser main page - redirect to hybrid version"""
    return redirect(url_for('cli_browser_hybrid'))


@app.route('/cli-browser/classic')
@login_required
def cli_browser_classic():
    """CLI command browser classic mode-based page"""
    try:
        stats = cli_browser_mgr.get_statistics()
        categories = cli_browser_mgr.get_mode_categories()

        return render_template('cli_browser.html',
                             stats=stats,
                             categories=categories)
    except Exception as e:
        flash(f'Error loading CLI browser: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))


@app.route('/cli-browser/hybrid')
@login_required
def cli_browser_hybrid():
    """CLI command browser with hybrid navigation"""
    try:
        stats = cli_browser_mgr.get_statistics()

        return render_template('cli_browser_hybrid.html', stats=stats)
    except Exception as e:
        flash(f'Error loading CLI browser: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))


@app.route('/api/cli/modes')
@login_required
def api_cli_modes():
    """Get all CLI modes with optional category filter"""
    try:
        category = request.args.get('category')
        modes = cli_browser_mgr.get_modes(category=category)
        
        return jsonify({
            'total': len(modes),
            'modes': [mode.to_dict() for mode in modes]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/cli/modes/categories')
@login_required
def api_cli_mode_categories():
    """Get modes grouped by category"""
    try:
        categories = cli_browser_mgr.get_mode_categories()
        
        # Convert to JSON-serializable format
        result = {}
        for category, modes in categories.items():
            result[category] = [mode.to_dict() for mode in modes]
        
        return jsonify({
            'categories': result,
            'total': len(categories)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/cli/commands/<mode_name>')
@login_required
def api_cli_commands(mode_name):
    """Get commands for a specific mode"""
    try:
        limit = request.args.get('limit', 100, type=int)
        commands = cli_browser_mgr.get_commands_by_mode(mode_name, limit=limit)
        
        return jsonify({
            'mode': mode_name,
            'total': len(commands),
            'commands': [cmd.to_dict() for cmd in commands]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/cli/next-tokens', methods=['POST'])
@login_required
def api_cli_next_tokens():
    """Get next valid tokens for progressive disclosure"""
    try:
        data = request.get_json()
        mode_name = data.get('mode')
        current_tokens = data.get('tokens', [])
        
        if not mode_name:
            return jsonify({'error': 'mode is required'}), 400
        
        next_tokens = cli_navigator.get_next_tokens(mode_name, current_tokens)
        
        return jsonify({
            'mode': mode_name,
            'current_tokens': current_tokens,
            'next_tokens': [token.to_dict() for token in next_tokens],
            'count': len(next_tokens)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/cli/search')
@login_required
def api_cli_search():
    """Search commands (basic text search)"""
    try:
        query = request.args.get('q', '')
        limit = request.args.get('limit', 50, type=int)

        if not query:
            return jsonify({'error': 'query parameter q is required'}), 400

        results = cli_browser_mgr.search_commands(query, limit=limit)

        return jsonify({
            'query': query,
            'total': len(results),
            'results': [cmd.to_dict() for cmd in results]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/cli/semantic-search')
@login_required
def api_cli_semantic_search():
    """
    Semantic search across all CLI commands
    Global search not restricted by technology/category
    """
    try:
        query = request.args.get('q', '')
        limit = request.args.get('limit', 50, type=int)

        if not query:
            return jsonify({'error': 'query parameter q is required'}), 400

        if len(query) < 2:
            return jsonify({'error': 'query must be at least 2 characters'}), 400

        results = cli_browser_mgr.semantic_search(query, limit=limit)

        return jsonify({
            'query': query,
            'total': len(results),
            'results': results,
            'search_type': 'semantic'
        })
    except Exception as e:
        app.logger.error(f"Semantic search error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/cli/validate', methods=['POST'])
@login_required
def api_cli_validate():
    """Validate command syntax"""
    try:
        data = request.get_json()
        mode_name = data.get('mode')
        tokens = data.get('tokens', [])
        
        if not mode_name:
            return jsonify({'error': 'mode is required'}), 400
        
        is_valid, error_msg = cli_navigator.validate_command(mode_name, tokens)
        
        return jsonify({
            'valid': is_valid,
            'error': error_msg,
            'command': ' '.join(tokens)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/cli/stats')
@login_required
def api_cli_stats():
    """Get CLI browser statistics"""
    try:
        stats = cli_browser_mgr.get_statistics()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/cli/explain', methods=['POST'])
@login_required
def api_cli_explain():
    """Get AI explanation for command (stub for Phase 4)"""
    try:
        data = request.get_json()
        command = data.get('command')
        mode = data.get('mode')

        if not command:
            return jsonify({'error': 'command is required'}), 400

        # TODO: Implement AI explanation in Phase 4
        return jsonify({
            'command': command,
            'mode': mode,
            'explanation': 'AI explanation feature coming in Phase 4',
            'source': 'placeholder',
            'cached': False
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== Technology-Based Navigation API Routes ====================

@app.route('/api/cli/technologies')
@login_required
def api_cli_technologies():
    """Get all technology categories with command counts"""
    try:
        import sqlite3
        import json
        from collections import defaultdict

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Get all commands with technology tags
        cursor.execute("""
            SELECT technology_tags, action_tags
            FROM cli_commands
            WHERE technology_tags IS NOT NULL
        """)

        tech_counts = defaultdict(int)
        action_counts = defaultdict(lambda: defaultdict(int))

        for row in cursor.fetchall():
            tech_tags_json, action_tags_json = row

            if tech_tags_json:
                tech_tags = json.loads(tech_tags_json)
                action_tags = json.loads(action_tags_json) if action_tags_json else []

                for tech in tech_tags:
                    tech_counts[tech] += 1
                    for action in action_tags:
                        action_counts[tech][action] += 1

        conn.close()

        # Format response
        technologies = []
        for tech, count in sorted(tech_counts.items(), key=lambda x: x[1], reverse=True):
            technologies.append({
                'name': tech,
                'count': count,
                'actions': dict(action_counts[tech])
            })

        return jsonify({
            'total': len(technologies),
            'technologies': technologies
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/cli/technology/<tech_name>')
@login_required
def api_cli_technology_commands(tech_name):
    """Get commands for a specific technology"""
    try:
        import sqlite3
        import json

        action_filter = request.args.get('action')
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Build query with strong deduplication using GROUP BY
        query = """
            SELECT c.command_text,
                   MIN(c.command_base) as command_base,
                   MIN(c.technology_tags) as technology_tags,
                   MIN(c.action_tags) as action_tags,
                   MIN(m.mode_name) as mode_name,
                   MIN(m.mode_category) as mode_category
            FROM cli_commands c
            JOIN cli_modes m ON c.mode_id = m.mode_id
            WHERE c.technology_tags LIKE ?
        """
        params = [f'%"{tech_name}"%']

        if action_filter:
            query += " AND c.action_tags LIKE ?"
            params.append(f'%"{action_filter}"%')

        # Group by command_text to eliminate duplicates at database level
        query += """
            GROUP BY c.command_text
            ORDER BY
                CASE
                    WHEN c.command_text NOT LIKE '%<%' AND c.command_text NOT LIKE '%[%' THEN 0
                    ELSE 1
                END,
                LENGTH(c.command_text)
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cursor.execute(query, params)

        commands = []
        seen_commands = set()  # Track to ensure uniqueness

        for row in cursor.fetchall():
            cmd_text, cmd_base, tech_tags, action_tags, mode_name, mode_cat = row

            # Create unique key to prevent duplicates
            unique_key = f"{cmd_text}|{mode_name}"
            if unique_key in seen_commands:
                continue
            seen_commands.add(unique_key)

            commands.append({
                'command_text': cmd_text,
                'command_base': cmd_base,
                'description': None,  # TODO: JOIN with cli_command_docs for descriptions
                'technologies': json.loads(tech_tags) if tech_tags else [],
                'actions': json.loads(action_tags) if action_tags else [],
                'mode_name': mode_name,
                'mode_category': mode_cat
            })

        # Get total count of unique commands
        count_query = """
            SELECT COUNT(DISTINCT command_text)
            FROM cli_commands
            WHERE technology_tags LIKE ?
        """
        count_params = [f'%"{tech_name}"%']

        if action_filter:
            count_query += " AND action_tags LIKE ?"
            count_params.append(f'%"{action_filter}"%')

        cursor.execute(count_query, count_params)
        total = cursor.fetchone()[0]

        conn.close()

        return jsonify({
            'technology': tech_name,
            'action_filter': action_filter,
            'total': total,
            'limit': limit,
            'offset': offset,
            'commands': commands
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/cli/technology/<tech_name>/stats')
@login_required
def api_cli_technology_stats(tech_name):
    """Get statistics for a specific technology"""
    try:
        import sqlite3
        import json
        from collections import defaultdict

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT c.action_tags, m.mode_name
            FROM cli_commands c
            JOIN cli_modes m ON c.mode_id = m.mode_id
            WHERE c.technology_tags LIKE ?
        """, [f'%"{tech_name}"%'])

        action_counts = defaultdict(int)
        mode_counts = defaultdict(int)

        for row in cursor.fetchall():
            action_tags_json, mode_name = row

            if action_tags_json:
                action_tags = json.loads(action_tags_json)
                for action in action_tags:
                    action_counts[action] += 1

            mode_counts[mode_name] += 1

        conn.close()

        return jsonify({
            'technology': tech_name,
            'actions': dict(action_counts),
            'modes': dict(sorted(mode_counts.items(), key=lambda x: x[1], reverse=True)[:10])
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== Error Handlers ====================

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

# ==================== Telemetry API ====================

@app.route('/api/telemetry/debug/<hostname>')
@login_required
def api_telemetry_debug(hostname):
    """Debug telemetry collection for a specific device"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT ip_address, management_type FROM devices WHERE hostname = ?", (hostname,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({'error': 'Device not found'}), 404

        ip, mgmt_type = row
        username = os.environ.get('DEFAULT_DEVICE_USERNAME', 'admin')
        password = os.environ.get('DEFAULT_DEVICE_PASSWORD', '')

        debug_info = {
            'hostname': hostname,
            'ip': ip,
            'mgmt_type': mgmt_type,
            'steps': []
        }

        # Test connection and commands
        if mgmt_type == 'eapi':
            from connectors.eapi_connector import EAPIConnector
            connector = EAPIConnector(ip, username, password)

            debug_info['steps'].append({'step': 'Connecting via eAPI', 'status': 'attempting'})
            if connector.connect():
                debug_info['steps'].append({'step': 'Connection', 'status': 'success'})

                # Test show version
                debug_info['steps'].append({'step': 'Executing show version', 'status': 'attempting'})
                try:
                    result = connector.execute_commands(['show version'])
                    debug_info['steps'].append({
                        'step': 'show version',
                        'status': 'success',
                        'result_type': str(type(result)),
                        'result_length': len(result) if result else 0,
                        'first_item_type': str(type(result[0])) if result and len(result) > 0 else 'N/A',
                        'first_item_keys': list(result[0].keys()) if result and len(result) > 0 and isinstance(result[0], dict) else 'N/A',
                        'sample_data': str(result[0])[:500] if result and len(result) > 0 else 'Empty result'
                    })
                except Exception as e:
                    debug_info['steps'].append({'step': 'show version', 'status': 'failed', 'error': str(e)})

        elif mgmt_type == 'ssh':
            connector = NetmikoConnector(ip, username, password)

            debug_info['steps'].append({'step': 'Connecting via SSH', 'status': 'attempting'})
            if connector.connect():
                debug_info['steps'].append({'step': 'Connection', 'status': 'success'})

                # Test show version
                debug_info['steps'].append({'step': 'Executing show version', 'status': 'attempting'})
                try:
                    output = connector.execute_command('show version')
                    debug_info['steps'].append({
                        'step': 'show version',
                        'status': 'success',
                        'output_length': len(output),
                        'sample_output': output[:500]
                    })
                except Exception as e:
                    debug_info['steps'].append({'step': 'show version', 'status': 'failed', 'error': str(e)})

                connector.disconnect()

        return jsonify(debug_info)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/telemetry/devices', methods=['GET', 'POST'])
@login_required
def api_telemetry_devices():
    """Collect live telemetry from all devices and update the shared cache."""
    try:
        body = request.get_json(silent=True) or {}
        username = body.get('username') or os.environ.get('DEFAULT_DEVICE_USERNAME', 'admin')
        password = body.get('password') or os.environ.get('DEFAULT_DEVICE_PASSWORD', '')

        telemetry_data = _collect_all_telemetry(username, password)

        # Keep the shared cache warm so other pages / returning users see fresh data
        if telemetry_data:
            _write_telemetry_cache(telemetry_data)

        return jsonify({'success': True, 'devices': telemetry_data})

    except Exception as e:
        app.logger.error(f"Telemetry API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/devices/<hostname>/live-metrics')
@login_required
def api_live_metrics(hostname):
    """Return live metrics for a single device section (lazy-loaded by the Metrics tab)."""
    section  = request.args.get('section', 'interfaces')
    username = request.args.get('username') or os.environ.get('DEFAULT_DEVICE_USERNAME', 'admin')
    password = request.args.get('password', os.environ.get('DEFAULT_DEVICE_PASSWORD', ''))

    device = inventory_mgr.get_device(hostname)
    if not device:
        return jsonify({'error': 'Device not found'}), 404

    mgmt = device.management_type.value
    ip   = device.ip_address

    try:
        if mgmt == 'eapi':
            connector = EAPIConnector(ip, username, password, timeout=15)
            if not connector.connect():
                return jsonify({'error': 'eAPI connection failed'}), 503
            data = _live_metrics_eapi(connector, section)

        elif mgmt == 'ssh':
            connector = NetmikoConnector(ip, username, password, timeout=15)
            if not connector.connect():
                return jsonify({'error': 'SSH connection failed'}), 503
            data = _live_metrics_ssh(connector, section)
            connector.disconnect()

        elif mgmt == 'gnmi':
            from connectors.gnmi_connector import GNMIConnector
            port = int(device.gnmi_port) if device.gnmi_port else 6030
            connector = GNMIConnector(ip, port=port, username=username, password=password, timeout=15)
            if not connector.connect():
                return jsonify({'error': 'gNMI connection failed'}), 503
            try:
                data = _live_metrics_gnmi(connector, section)
            finally:
                connector.disconnect()

        else:
            return jsonify({'success': True, 'section': section,
                            'data': None, 'unavailable': True,
                            'reason': f'Live metrics not available for {mgmt} management type'})

        return jsonify({'success': True, 'section': section, 'data': data})

    except Exception as e:
        app.logger.error(f"Live metrics error [{hostname}/{section}]: {e}")
        return jsonify({'error': str(e)}), 500


def _live_metrics_eapi(connector, section):
    """Collect one metrics section via eAPI JSON commands."""

    def _result(res, idx=0):
        """Unwrap the pyeapi response envelope to get the actual result dict.

        pyeapi Node.enable() returns a list of dicts shaped:
            {'command': '...', 'encoding': 'json', 'result': {actual data}}
        Some commands (e.g. show lldp neighbors detail on older vEOS) return
        text output — in that case result['result'] is a string, not a dict.
        Always return a dict so callers can safely call .get() on the return value.
        """
        if not res or idx >= len(res):
            return {}
        item = res[idx]
        if not isinstance(item, dict):
            return {}
        r = item.get('result', {})
        return r if isinstance(r, dict) else {}

    if section == 'interfaces':
        res = connector.execute_commands(['show interfaces', 'show interfaces counters rates'])
        intfs_raw = _result(res, 0).get('interfaces', {})
        rates_raw = _result(res, 1).get('interfaces', {})
        rows = []
        for name, d in sorted(intfs_raw.items()):
            if name.startswith('Management'):
                continue
            ctr   = d.get('interfaceCounters', {})
            rates = rates_raw.get(name, {})
            rows.append({
                'name':        name,
                'status':      d.get('interfaceStatus', ''),
                'line_proto':  d.get('lineProtocolStatus', ''),
                'description': d.get('description', ''),
                'bandwidth':   d.get('bandwidth', 0),
                'in_errors':   ctr.get('totalInErrors', ctr.get('inErrors', 0)),
                'out_errors':  ctr.get('totalOutErrors', ctr.get('outErrors', 0)),
                'in_octets':   ctr.get('inOctets', 0),
                'out_octets':  ctr.get('outOctets', 0),
                'in_bps':      rates.get('inBitsRate', 0),
                'out_bps':     rates.get('outBitsRate', 0),
            })
        return {'interfaces': rows}

    elif section == 'bgp':
        res = connector.execute_commands(['show ip bgp summary'])
        vrfs_raw = _result(res).get('vrfs', {})
        vrfs = {}
        for vrf_name, vrf in vrfs_raw.items():
            peers = []
            for peer_ip, p in vrf.get('peers', {}).items():
                peers.append({
                    'neighbor':          peer_ip,
                    'asn':               p.get('asn', ''),
                    'state':             p.get('peerState', ''),
                    'prefixes_received': p.get('prefixReceived', 0),
                    'uptime':            p.get('upDownTime', 0),
                    'msg_rcvd':          p.get('msgReceived', 0),
                    'msg_sent':          p.get('msgSent', 0),
                })
            vrfs[vrf_name] = {'router_id': vrf.get('routerId', ''), 'peers': peers}
        return {'vrfs': vrfs}

    elif section == 'lldp':
        res = connector.execute_commands(['show lldp neighbors detail'])
        neighbors_raw = _result(res).get('lldpNeighbors', [])
        neighbors = []
        for n in neighbors_raw:
            caps = n.get('systemCapabilities', {})
            cap_str = ', '.join(k[:1].upper() for k, v in caps.items() if v)
            neighbors.append({
                'local_port':    n.get('port', ''),
                'neighbor':      n.get('neighborDevice', ''),
                'neighbor_port': n.get('neighborPort', ''),
                'description':   n.get('neighborPortDescription', ''),
                'capabilities':  cap_str,
            })
        return {'neighbors': neighbors}

    elif section == 'routing':
        res = connector.execute_commands(['show ip route summary'])
        vrfs_raw = _result(res).get('vrfs', {})
        vrfs = {}
        for vrf_name, vrf in vrfs_raw.items():
            protocols = {}
            for proto, pdata in vrf.get('routes', {}).items():
                count = pdata.get('total', pdata) if isinstance(pdata, dict) else int(pdata)
                if count:
                    protocols[proto] = count
            vrfs[vrf_name] = {
                'total':     vrf.get('allRoutes', sum(protocols.values())),
                'protocols': protocols,
            }
        return {'vrfs': vrfs}

    elif section == 'environment':
        res = connector.execute_commands(['show system environment all'])
        data = _result(res)

        temp_sensors = []
        for s in data.get('tempSensors', []):
            temp_sensors.append({
                'name':     s.get('name', ''),
                'current':  s.get('currentTemperature', 0),
                'warning':  s.get('overheatThreshold', 75),
                'critical': s.get('criticalThreshold', 95),
                'status':   'warning' if s.get('inAlertState') else 'ok',
            })

        psus = []
        for slot, p in data.get('powerSupplies', {}).items():
            psus.append({
                'slot':             slot,
                'state':            p.get('state', ''),
                'output_watts':     round(p.get('outputPower', 0), 1),
                'capacity_watts':   p.get('capacity', 0),
            })

        fans = []
        for slot, f in data.get('fans', {}).items():
            fans.append({
                'slot':      slot,
                'status':    f.get('status', ''),
                'speed_pct': f.get('speed', 0),
            })

        return {'temperature': temp_sensors, 'power_supplies': psus, 'fans': fans}

    return {}


def _live_metrics_ssh(connector, section):
    """Collect one metrics section via SSH text output."""
    if section == 'interfaces':
        out = connector.execute_command('show interfaces status')
        rows = []
        for line in out.splitlines():
            parts = line.split()
            if not parts or not (parts[0].startswith('Et') or parts[0].startswith('Po')):
                continue
            rows.append({
                'name':       parts[0],
                'status':     parts[2] if len(parts) > 2 else '',
                'line_proto': '',
                'description': ' '.join(parts[3:-2]) if len(parts) > 5 else '',
                'bandwidth':  0, 'in_errors': 0, 'out_errors': 0,
                'in_octets': 0, 'out_octets': 0, 'in_bps': 0, 'out_bps': 0,
            })
        return {'interfaces': rows}

    elif section == 'bgp':
        out = connector.execute_command('show ip bgp summary')
        peers = []
        in_peers = False
        for line in out.splitlines():
            if 'Neighbor' in line and 'AS' in line:
                in_peers = True
                continue
            if in_peers and line.strip():
                parts = line.split()
                if len(parts) >= 9 and '.' in parts[0]:
                    peers.append({
                        'neighbor': parts[0], 'asn': parts[2],
                        'state': parts[8], 'prefixes_received': 0,
                        'uptime': parts[7], 'msg_rcvd': 0, 'msg_sent': 0,
                    })
        return {'vrfs': {'default': {'router_id': '', 'peers': peers}}}

    elif section == 'lldp':
        out = connector.execute_command('show lldp neighbors')
        neighbors = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0].startswith('Et'):
                neighbors.append({
                    'local_port': parts[0], 'neighbor': parts[1],
                    'neighbor_port': parts[2], 'description': '',
                    'capabilities': parts[3] if len(parts) > 3 else '',
                })
        return {'neighbors': neighbors}

    elif section == 'routing':
        out = connector.execute_command('show ip route summary')
        total, protocols = 0, {}
        for line in out.splitlines():
            m = re.search(r'Total Routes:\s*(\d+)', line)
            if m:
                total = int(m.group(1))
            for proto in ('connected', 'static', 'ospf', 'bgp', 'isis'):
                m = re.search(rf'{proto}\s+(\d+)', line, re.IGNORECASE)
                if m:
                    protocols[proto] = int(m.group(1))
        return {'vrfs': {'default': {'total': total, 'protocols': protocols}}}

    elif section == 'environment':
        out = connector.execute_command('show system environment all')
        return {'temperature': DeviceTelemetry.parse_temperature(out).get('sensors', []),
                'power_supplies': [], 'fans': []}

    return {}


def _live_metrics_gnmi(connector, section):
    """Collect one metrics section via gNMI eos_native paths."""

    def _notifications(result):
        """Yield (prefix_last_segment, {leaf: val}) for each notification."""
        if not result:
            return
        for notif in result.get('notification', []):
            prefix = notif.get('prefix', '')
            entity = prefix.rstrip('/').split('/')[-1]
            if not entity or entity.startswith('_'):
                continue
            updates = {u['path']: u['val'] for u in notif.get('update', [])}
            yield entity, updates

    if section == 'interfaces':
        result = connector.get('eos_native:/Sysdb/interface/status/eth/phy/slice/1/intfStatus')
        rows = []
        for name, upd in _notifications(result):
            if name == 'intfStatus':
                continue
            oper = upd.get('operStatus', '')
            rows.append({
                'name':        name,
                'status':      'connected' if oper == 'intfOperUp' else 'notconnect',
                'line_proto':  'up' if oper == 'intfOperUp' else 'down',
                'description': upd.get('description', ''),
                'bandwidth':   upd.get('bandwidth', 0),
                'in_errors':   0,
                'out_errors':  0,
                'in_octets':   0,
                'out_octets':  0,
                'in_bps':      0,
                'out_bps':     0,
            })
        rows.sort(key=lambda r: r['name'])
        return {'interfaces': rows}

    elif section == 'bgp':
        result = connector.get('eos_native:/Sysdb/routing/bgp/export')
        peers = []
        for peer_ip, upd in _notifications(result):
            # Skip non-peer entries (no peerState)
            if 'peerState' not in upd:
                continue
            peers.append({
                'neighbor':          peer_ip,
                'asn':               upd.get('peerAs', ''),
                'state':             upd.get('peerState', ''),
                'prefixes_received': upd.get('prefixesReceived', 0),
                'uptime':            upd.get('establishedTime', 0),
                'msg_rcvd':          0,
                'msg_sent':          0,
            })
        return {'vrfs': {'default': {'router_id': '', 'peers': peers}}}

    elif section == 'lldp':
        result = connector.get('eos_native:/Sysdb/l2discovery/lldp/status/local/port')
        neighbors = []
        for port_name, upd in _notifications(result):
            neighbor = upd.get('systemName', upd.get('chassisId', ''))
            neighbor_port = upd.get('portId', '')
            if not neighbor and not neighbor_port:
                continue
            neighbors.append({
                'local_port':    port_name,
                'neighbor':      neighbor,
                'neighbor_port': neighbor_port,
                'description':   upd.get('portDescription', ''),
                'capabilities':  '',
            })
        return {'neighbors': neighbors}

    elif section == 'routing':
        # Routing table not reliably available via eos_native on vEOS-lab
        return {'vrfs': {}}

    elif section == 'environment':
        paths = [
            'eos_native:/Sysdb/environment/temperature/sensor',
            'eos_native:/Sysdb/cpu/utilization/cpuInfo/0/cpuUtilization',
            'eos_native:/Sysdb/kernel/procfs/meminfo',
        ]
        result = connector.get_multi(paths)

        # Temperature sensors
        temp_sensors = []
        for sensor_name, upd in _notifications(result):
            if 'currentTemperature' not in upd and 'temperature' not in upd:
                continue
            current = upd.get('currentTemperature', upd.get('temperature', 0))
            temp_sensors.append({
                'name':     sensor_name,
                'current':  current,
                'warning':  upd.get('overheatThreshold', 75),
                'critical': upd.get('criticalThreshold', 95),
                'status':   'warning' if upd.get('inAlertState') else 'ok',
            })

        # CPU — expect a single notification with idle leaf
        cpu_percent = None
        mem_percent = None
        for entity, upd in _notifications(result):
            if 'idle' in upd:
                idle = upd.get('idle', 0)
                cpu_percent = round(100 - idle, 1)
            if 'memTotal' in upd:
                total = upd.get('memTotal', 0)
                free  = upd.get('memFree', 0)
                buff  = upd.get('buffers', 0)
                cached = upd.get('cached', 0)
                if total:
                    used = total - free - buff - cached
                    mem_percent = round(used / total * 100, 1)

        out = {
            'temperature':    temp_sensors,
            'power_supplies': [],
            'fans':           [],
        }
        if cpu_percent is not None:
            out['cpu_percent'] = cpu_percent
        if mem_percent is not None:
            out['mem_percent'] = mem_percent
        return out

    return {}


@app.route('/api/telemetry/cached')
@login_required
def api_telemetry_cached():
    """Return the last background-collected telemetry instantly (no device connections)."""
    import json as _json
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT devices_json, updated_at FROM telemetry_cache WHERE id=1")
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({'success': True, 'devices': [], 'age': None, 'from_cache': True})

        devices = _json.loads(row[0])
        age = int(time.time() - row[1])
        return jsonify({'success': True, 'devices': devices, 'age': age, 'from_cache': True})

    except Exception as e:
        app.logger.error(f"Telemetry cache read error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/devices/status')
@login_required
def api_devices_status():
    """Fast TCP port-based device status check (works in Docker, faster than ICMP)"""
    import socket

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT hostname, ip_address, management_type, gnmi_port FROM devices")

        device_status = []
        for row in cursor.fetchall():
            hostname, ip, mgmt_type, gnmi_port = row

            # Determine which port to check based on management type
            if mgmt_type == 'eapi':
                ports = [443, 80]
            elif mgmt_type == 'gnmi':
                ports = [int(gnmi_port) if gnmi_port else 6030]
            else:  # ssh or cvp
                ports = [22]

            reachable = False
            for port in ports:
                try:
                    # Quick TCP connection test with 2 second timeout
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)
                    result = sock.connect_ex((ip, port))
                    sock.close()

                    if result == 0:
                        reachable = True
                        break
                except socket.timeout:
                    continue
                except Exception as e:
                    app.logger.debug(f"Port check failed for {hostname} ({ip}:{port}): {e}")
                    continue

            device_status.append({
                'hostname': hostname,
                'ip': ip,
                'reachable': reachable
            })

        conn.close()
        return jsonify({'success': True, 'devices': device_status})

    except Exception as e:
        app.logger.error(f"Device status check error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== Settings API ====================

@app.route('/api/settings/grouping', methods=['POST'])
@login_required
def api_settings_grouping():
    """Save grouping pattern settings"""
    data = request.json
    session['groupSeparator'] = data.get('separator', '-')
    session['customPattern'] = data.get('customPattern', '')
    return jsonify({'success': True})

@app.route('/api/configlets/bulk-delete', methods=['POST'])
@login_required
def api_configlets_bulk_delete():
    """Delete multiple configlets"""
    data = request.json
    names = data.get('names', [])
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for name in names:
        cursor.execute("DELETE FROM configlets WHERE name = ?", (name,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'deleted': len(names)})

@app.route('/api/configlets/export')
@login_required
def api_configlets_export():
    """Export multiple configlets as zip"""
    import zipfile
    from io import BytesIO
    names = request.args.get('names', '').split(',')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zf:
        for name in names:
            cursor.execute("SELECT content FROM configlets WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                zf.writestr(f"{name}.conf", row[0])

    conn.close()
    buffer.seek(0)
    return send_file(buffer, mimetype='application/zip', as_attachment=True, download_name='configlets.zip')

@app.route('/api/configlet-groups', methods=['GET', 'POST'])
@login_required
def api_configlet_groups():
    """Manage custom groups"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if request.method == 'POST':
        data = request.json
        cursor.execute("INSERT INTO configlet_groups (name, description, color) VALUES (?, ?, ?)",
                      (data['name'], data.get('description', ''), data.get('color', 'primary')))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    else:
        cursor.execute("SELECT id, name, description, color FROM configlet_groups ORDER BY name")
        groups = [{'id': r[0], 'name': r[1], 'description': r[2], 'color': r[3]} for r in cursor.fetchall()]
        conn.close()
        return jsonify(groups)

@app.route('/api/configlet-groups/<int:group_id>', methods=['DELETE'])
@login_required
def api_delete_configlet_group(group_id):
    """Delete a group"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM configlet_groups WHERE id = ?", (group_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/configlets/assign-group', methods=['POST'])
@login_required
def api_assign_configlets_to_group():
    """Assign configlets to a group"""
    data = request.json
    configlets = data.get('configlets', [])
    group_id = data.get('groupId')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for name in configlets:
        cursor.execute("INSERT OR REPLACE INTO configlet_group_assignments (configlet_name, group_id) VALUES (?, ?)",
                      (name, group_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/configlets/search')
@login_required
def api_configlets_search():
    """Search configlets via AJAX"""
    try:
        from database.db_manager import DBManager
        from collections import defaultdict
        import re

        db = DBManager(DB_PATH)
        configlets = db.get_all_configlets()

        search = request.args.get('search', '').strip()
        filter_type = request.args.get('filter_type', '').strip()
        filter_group = request.args.get('filter_group', '').strip()
        group_by = request.args.get('group_by', 'name')

        configlets_list = [{
            'name': cfg.name,
            'type': cfg.configlet_type or 'static',
            'description': cfg.description or '',
            'lines': len(cfg.config.split('\n'))
        } for cfg in configlets]

        # Apply filters
        if search:
            configlets_list = [c for c in configlets_list if search.lower() in c['name'].lower() or search.lower() in c.get('description', '').lower()]
        if filter_type:
            configlets_list = [c for c in configlets_list if c.get('type') == filter_type]

        def get_group_name(name):
            separator = session.get('groupSeparator', '-')
            custom_pattern = session.get('customPattern', '')
            if separator == 'custom' and custom_pattern:
                try:
                    match = re.match(custom_pattern, name)
                    return match.group(1) if match and len(match.groups()) > 0 else 'Other'
                except:
                    return 'Other'
            elif separator in name:
                return name.split(separator)[0]
            else:
                return 'Other'

        if filter_group:
            configlets_list = [c for c in configlets_list if get_group_name(c['name']) == filter_group]

        # Group results
        grouped = defaultdict(list)
        if group_by == 'name':
            for cfg in configlets_list:
                grouped[get_group_name(cfg['name'])].append(cfg)
        elif group_by == 'type':
            for cfg in configlets_list:
                grouped[cfg['type']].append(cfg)
        else:
            grouped['All Configlets'] = configlets_list

        for group in grouped:
            grouped[group].sort(key=lambda x: x['name'])

        return jsonify({
            'success': True,
            'grouped_configlets': dict(grouped),
            'total': len(configlets_list)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== Device Metrics (Prometheus) ====================

@app.route('/api/metrics/<hostname>')
@login_required
def api_device_metrics(hostname):
    """Query Prometheus for gNMI streaming telemetry for a device."""
    import requests as http_req

    prom_url = os.environ.get('PROMETHEUS_URL', 'http://localhost:9091')
    range_param = request.args.get('range', '1h')

    range_map = {'1h': 3600, '6h': 21600, '24h': 86400}
    if range_param not in range_map:
        range_param = '1h'
    seconds = range_map[range_param]

    end_ts = int(time.time())
    start_ts = end_ts - seconds
    # ~120 data points max, aligned to gnmic 30s sample interval
    step = max(30, seconds // 120)

    try:
        # ── Interface active status over time ──────────────────────────────
        active_q = (
            '{__name__=~"gnmic_Sysdb_interface_status_eth_phy_slice_1_intfStatus_Ethernet.*_active"'
            f',source="{hostname}"}}'
        )
        active_resp = http_req.get(
            f'{prom_url}/api/v1/query_range',
            params={'query': active_q, 'start': start_ts, 'end': end_ts, 'step': step},
            timeout=5
        )
        active_data = active_resp.json()

        if active_data['status'] != 'success' or not active_data['data']['result']:
            return jsonify({'has_data': False, 'source': hostname})

        active_history = {}
        interfaces = []
        for series in active_data['data']['result']:
            metric_name = series['metric']['__name__']
            parts = metric_name.split('_intfStatus_')
            if len(parts) == 2:
                intf = parts[1].replace('_active', '')
                interfaces.append(intf)
                active_history[intf] = [[v[0], int(v[1])] for v in series['values']]

        # Natural sort: Ethernet1, Ethernet2, …, Ethernet10, …
        def _intf_key(name):
            m = re.search(r'(\d+)$', name)
            return (name[:m.start()] if m else name, int(m.group(1)) if m else 0)
        interfaces.sort(key=_intf_key)

        # ── Link flap counters (current value) ────────────────────────────
        flaps_q = (
            '{__name__=~"gnmic_Sysdb_interface_status_eth_phy_slice_1_intfStatus_Ethernet.*_linkStatusChanges"'
            f',source="{hostname}"}}'
        )
        flaps_resp = http_req.get(
            f'{prom_url}/api/v1/query',
            params={'query': flaps_q},
            timeout=5
        )
        flaps_data = flaps_resp.json()

        link_flaps = {}
        if flaps_data['status'] == 'success':
            for series in flaps_data['data']['result']:
                metric_name = series['metric']['__name__']
                parts = metric_name.split('_intfStatus_')
                if len(parts) == 2:
                    intf = parts[1].replace('_linkStatusChanges', '')
                    link_flaps[intf] = int(float(series['value'][1]))

        return jsonify({
            'has_data': True,
            'source': hostname,
            'range': range_param,
            'interfaces': interfaces,
            'active_history': active_history,
            'link_flaps': link_flaps,
        })

    except Exception as e:
        return jsonify({'has_data': False, 'error': str(e), 'source': hostname})


# ==================== MIB Browser Routes ====================

@app.route('/mib-browser')
@login_required
def mib_browser():
    stats = mib_browser_mgr.get_stats()
    return render_template('mib_browser.html', stats=stats)


@app.route('/api/mib/modules')
@login_required
def api_mib_modules():
    return jsonify(mib_browser_mgr.get_modules_summary())


@app.route('/api/mib/module/<module_name>')
@login_required
def api_mib_module(module_name):
    mod = mib_browser_mgr.get_module(module_name)
    if not mod:
        return jsonify({'error': 'Module not found'}), 404
    return jsonify(mod)


@app.route('/api/mib/search')
@login_required
def api_mib_search():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    return jsonify(mib_browser_mgr.search(q))


# ==================== Device Groups ====================

@app.route('/api/device-groups', methods=['GET', 'POST'])
@login_required
def api_device_groups():
    """List or create device groups"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if request.method == 'POST':
        data = request.json or {}
        name = (data.get('name') or '').strip()
        hostnames = data.get('devices', [])
        if not name:
            conn.close()
            return jsonify({'success': False, 'error': 'Group name required'}), 400
        try:
            cursor.execute(
                "INSERT INTO device_groups (group_name) VALUES (?)", (name,)
            )
            group_id = cursor.lastrowid
            for h in hostnames:
                cursor.execute(
                    "INSERT OR IGNORE INTO device_group_members (group_id, device_hostname) VALUES (?, ?)",
                    (group_id, h)
                )
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'group_id': group_id})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({'success': False, 'error': 'Group name already exists'}), 409

    # GET — return all groups with their device lists
    cursor.execute("SELECT group_id, group_name FROM device_groups ORDER BY group_name")
    groups = []
    for gid, gname in cursor.fetchall():
        cursor.execute(
            "SELECT device_hostname FROM device_group_members WHERE group_id = ?", (gid,)
        )
        devices = [r[0] for r in cursor.fetchall()]
        groups.append({'group_id': gid, 'group_name': gname, 'devices': devices})
    conn.close()
    return jsonify(groups)


@app.route('/api/device-groups/<int:group_id>', methods=['PUT', 'DELETE'])
@login_required
def api_device_group(group_id):
    """Update or delete a device group"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if request.method == 'DELETE':
        cursor.execute("DELETE FROM device_groups WHERE group_id = ?", (group_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    # PUT — update name and membership
    data = request.json or {}
    name = (data.get('name') or '').strip()
    hostnames = data.get('devices', [])
    if not name:
        conn.close()
        return jsonify({'success': False, 'error': 'Group name required'}), 400
    try:
        cursor.execute(
            "UPDATE device_groups SET group_name = ? WHERE group_id = ?", (name, group_id)
        )
        cursor.execute(
            "DELETE FROM device_group_members WHERE group_id = ?", (group_id,)
        )
        for h in hostnames:
            cursor.execute(
                "INSERT OR IGNORE INTO device_group_members (group_id, device_hostname) VALUES (?, ?)",
                (group_id, h)
            )
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'error': 'Group name already exists'}), 409


# ==================== Main ====================

if __name__ == '__main__':
    # Development server
    app.run(host='0.0.0.0', port=5000, debug=True)
