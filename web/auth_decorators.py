"""
Authentication Decorators
Enhanced decorators for route protection
"""

from functools import wraps
from flask import session, redirect, url_for, flash, request


def login_required(f):
    """Require user to be logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Require user to be logged in as admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page', 'warning')
            return redirect(url_for('login'))

        if not session.get('is_admin'):
            flash('Administrator access required', 'danger')
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)
    return decorated_function
