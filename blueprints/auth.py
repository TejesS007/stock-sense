from datetime import datetime, timedelta, timezone
from functools import wraps
import random
from flask import Blueprint, render_template, redirect, url_for, request, session, flash, g
from models import db, User

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def login_required(view_func):
    """Decorator to require login for protected routes."""
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if 'user_id' not in session:
            # Preserve requested URL for redirection after login
            return redirect(url_for('auth.login', next=request.path))
        return view_func(*args, **kwargs)
    return wrapped_view


@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session:
        return redirect(url_for('dashboard.index'))

    errors = {}
    form_data = {
        'login_id': '',
        'email': ''
    }

    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        form_data['login_id'] = login_id
        form_data['email'] = email

        # Validations
        if not login_id:
            errors['login_id'] = 'Login ID is required.'
        elif len(login_id) < 3:
            errors['login_id'] = 'Login ID must be at least 3 characters.'
        else:
            # Check login_id uniqueness
            existing_user = User.query.filter_by(login_id=login_id).first()
            if existing_user:
                errors['login_id'] = 'This Login ID is already taken.'

        if not email:
            errors['email'] = 'Email address is required.'
        elif '@' not in email or '.' not in email:
            errors['email'] = 'Please enter a valid email address.'
        else:
            # Check email uniqueness
            existing_email = User.query.filter_by(email=email).first()
            if existing_email:
                errors['email'] = 'This email address is already registered.'

        if not password:
            errors['password'] = 'Password is required.'
        elif len(password) < 4:
            errors['password'] = 'Password must be at least 4 characters.'

        if not errors:
            user = User(login_id=login_id, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('auth.login', login_id=login_id))

        return render_template('auth/signup.html', form_data=form_data, errors=errors), 400

    return render_template('auth/signup.html', form_data=form_data, errors=errors)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard.index'))

    errors = {}
    next_url = request.args.get('next') or request.form.get('next') or ''
    form_data = {
        'login_id': request.args.get('login_id', '')
    }

    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        password = request.form.get('password', '')
        form_data['login_id'] = login_id

        if not login_id:
            errors['login_id'] = 'Login ID is required.'
        if not password:
            errors['password'] = 'Password is required.'

        if not errors:
            user = User.query.filter_by(login_id=login_id).first()
            if not user or not user.check_password(password):
                errors['general'] = 'Invalid Login ID or password.'
            else:
                session.clear()
                session['user_id'] = user.id
                session['login_id'] = user.login_id

                flash(f'Welcome back, {user.login_id}!', 'success')

                if next_url and next_url.startswith('/') and not next_url.startswith('//'):
                    return redirect(next_url)
                return redirect(url_for('dashboard.index'))

        return render_template('auth/login.html', form_data=form_data, errors=errors, next_url=next_url), 400

    return render_template('auth/login.html', form_data=form_data, errors=errors, next_url=next_url)


@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    errors = {}
    form_data = {'login_id': ''}

    if request.method == 'POST':
        identifier = request.form.get('login_id', '').strip()
        form_data['login_id'] = identifier

        if not identifier:
            errors['login_id'] = 'Login ID or Email is required.'
            return render_template('auth/forgot_password.html', form_data=form_data, errors=errors), 400

        user = User.query.filter(
            (User.login_id == identifier) | (User.email == identifier.lower())
        ).first()

        if not user:
            errors['login_id'] = 'No account found with this Login ID or Email.'
            return render_template('auth/forgot_password.html', form_data=form_data, errors=errors), 400

        # Generate 6-digit OTP
        otp = f"{random.randint(100000, 999999):06d}"
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        expiry = now_utc + timedelta(minutes=10)

        user.reset_otp = otp
        user.reset_otp_expiry = expiry
        db.session.commit()

        # Mocked console output (as per spec)
        print("\n" + "=" * 65, flush=True)
        print(" [MOCK EMAIL/SMS CONSOLE LOG] PASSWORD RESET OTP", flush=True)
        print(f" User Login ID : {user.login_id}", flush=True)
        print(f" User Email    : {user.email}", flush=True)
        print(f" 6-Digit OTP   : {otp}", flush=True)
        print(f" Expiration    : {expiry.strftime('%Y-%m-%d %H:%M:%S UTC')} (10 minutes)", flush=True)
        print("=" * 65 + "\n", flush=True)

        flash(f'A 6-digit OTP was generated for {user.login_id} and logged to the server console.', 'info')
        return redirect(url_for('auth.reset_password', login_id=user.login_id))

    return render_template('auth/forgot_password.html', form_data=form_data, errors=errors)


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    errors = {}
    form_data = {
        'login_id': request.args.get('login_id', ''),
        'otp': ''
    }

    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        otp = request.form.get('otp', '').strip()
        new_password = request.form.get('new_password', '')

        form_data['login_id'] = login_id
        form_data['otp'] = otp

        if not login_id:
            errors['login_id'] = 'Login ID is required.'
        if not otp:
            errors['otp'] = '6-Digit OTP is required.'
        elif len(otp) != 6 or not otp.isdigit():
            errors['otp'] = 'OTP must be exactly 6 digits.'

        if not new_password:
            errors['new_password'] = 'New password is required.'
        elif len(new_password) < 4:
            errors['new_password'] = 'Password must be at least 4 characters.'

        if not errors:
            user = User.query.filter_by(login_id=login_id).first()
            if not user:
                errors['login_id'] = 'No account found with this Login ID.'
            elif not user.reset_otp or user.reset_otp != otp:
                errors['otp'] = 'Invalid OTP code. Please check the server console.'
            else:
                now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
                if not user.reset_otp_expiry or user.reset_otp_expiry < now_utc:
                    errors['otp'] = 'This OTP has expired (10-minute limit). Please request a new one.'
                else:
                    # Valid OTP: set new password and clear OTP
                    user.set_password(new_password)
                    user.reset_otp = None
                    user.reset_otp_expiry = None
                    db.session.commit()

                    flash('Password reset successful! Please log in with your new password.', 'success')
                    return redirect(url_for('auth.login', login_id=user.login_id))

        return render_template('auth/reset_password.html', form_data=form_data, errors=errors), 400

    return render_template('auth/reset_password.html', form_data=form_data, errors=errors)
