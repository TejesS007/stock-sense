import sys
from datetime import datetime, timedelta, timezone
from app import create_app
from models import db, User

app = create_app({
    'TESTING': True,
    'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    'WTF_CSRF_ENABLED': False
})

client = app.test_client()

with app.app_context():
    db.create_all()

    print("--- 1. Testing Unauthenticated Protection ---")
    protected_urls = [
        '/',
        '/dashboard',
        '/products/',
        '/products/create',
        '/stock/',
        '/operations/receipts/',
        '/operations/receipts/new',
        '/operations/delivery/',
        '/operations/delivery/new',
        '/operations/transfers/',
        '/operations/transfers/new',
        '/move-history/',
        '/settings/warehouse',
        '/settings/location',
    ]

    for url in protected_urls:
        resp = client.get(url)
        assert resp.status_code == 302, f"Expected 302 redirect for {url}, got {resp.status_code}"
        assert '/auth/login' in resp.headers['Location'], f"Expected redirect to /auth/login for {url}"
    print("All protected routes correctly redirected to /auth/login!")

    print("\n--- 2. Testing Signup ---")
    # Successful signup
    signup_resp = client.post('/auth/signup', data={
        'login_id': 'admin',
        'email': 'admin@stocksense.com',
        'password': 'password123'
    }, follow_redirects=False)
    assert signup_resp.status_code == 302, f"Signup should redirect on success, got {signup_resp.status_code}"

    user = User.query.filter_by(login_id='admin').first()
    assert user is not None, "User should exist in database"
    assert user.check_password('password123'), "Password hash should match"
    assert not user.check_password('wrongpass'), "Wrong password should fail"
    print("User successfully created with hashed password!")

    # Collision test - login_id
    dup_login_resp = client.post('/auth/signup', data={
        'login_id': 'admin',
        'email': 'different@stocksense.com',
        'password': 'password123'
    })
    assert dup_login_resp.status_code == 400
    assert b"This Login ID is already taken" in dup_login_resp.data, "Should show inline collision error for login_id"
    print("Collision on login_id caught and inline error displayed!")

    # Collision test - email
    dup_email_resp = client.post('/auth/signup', data={
        'login_id': 'otheruser',
        'email': 'admin@stocksense.com',
        'password': 'password123'
    })
    assert dup_email_resp.status_code == 400
    assert b"This email address is already registered" in dup_email_resp.data, "Should show inline collision error for email"
    print("Collision on email caught and inline error displayed!")

    print("\n--- 3. Testing Login ---")
    # Bad credentials
    bad_login_resp = client.post('/auth/login', data={
        'login_id': 'admin',
        'password': 'wrongpassword'
    })
    assert bad_login_resp.status_code == 400
    assert b"Invalid Login ID or password" in bad_login_resp.data
    print("Invalid login correctly rejected!")

    # Valid credentials
    good_login_resp = client.post('/auth/login', data={
        'login_id': 'admin',
        'password': 'password123'
    }, follow_redirects=False)
    assert good_login_resp.status_code == 302
    assert good_login_resp.headers['Location'].endswith('/') or '/dashboard' in good_login_resp.headers['Location']
    print("Valid login accepted and redirected to dashboard!")

    # Access protected route as authenticated user
    dash_resp = client.get('/')
    assert dash_resp.status_code == 200
    assert b"admin" in dash_resp.data, "Current user login_id should appear in topbar"
    print("Authenticated user successfully accessed dashboard!")

    print("\n--- 4. Testing Logout ---")
    logout_resp = client.get('/auth/logout', follow_redirects=False)
    assert logout_resp.status_code == 302
    assert '/auth/login' in logout_resp.headers['Location']

    # Now dashboard should redirect again
    dash_after_logout = client.get('/')
    assert dash_after_logout.status_code == 302
    print("Logout cleared session and re-locked protected routes!")

    print("\n--- 5. Testing Forgot Password & Reset Password ---")
    # Request OTP
    forgot_resp = client.post('/auth/forgot-password', data={'login_id': 'admin'}, follow_redirects=False)
    assert forgot_resp.status_code == 302
    assert '/auth/reset-password' in forgot_resp.headers['Location']

    user = User.query.filter_by(login_id='admin').first()
    assert user.reset_otp is not None, "Reset OTP should be generated"
    assert len(user.reset_otp) == 6, "OTP should be 6 digits"
    assert user.reset_otp_expiry > datetime.now(timezone.utc).replace(tzinfo=None), "OTP expiry should be in future"
    otp_code = user.reset_otp
    print(f"OTP generated: {otp_code}, expires: {user.reset_otp_expiry}")

    # Reset with wrong OTP
    wrong_otp_resp = client.post('/auth/reset-password', data={
        'login_id': 'admin',
        'otp': '000000',
        'new_password': 'newpassword456'
    })
    assert wrong_otp_resp.status_code == 400
    assert b"Invalid OTP code" in wrong_otp_resp.data
    print("Wrong OTP code correctly rejected!")

    # Reset with valid OTP
    good_reset_resp = client.post('/auth/reset-password', data={
        'login_id': 'admin',
        'otp': otp_code,
        'new_password': 'newpassword456'
    }, follow_redirects=False)
    assert good_reset_resp.status_code == 302
    assert '/auth/login' in good_reset_resp.headers['Location']

    user = User.query.filter_by(login_id='admin').first()
    assert user.reset_otp is None, "OTP should be cleared after successful reset"
    assert user.check_password('newpassword456'), "New password should be active"
    print("Password reset successful and OTP cleared!")

    # Login with new password
    login_new_resp = client.post('/auth/login', data={
        'login_id': 'admin',
        'password': 'newpassword456'
    }, follow_redirects=False)
    assert login_new_resp.status_code == 302
    print("Logged in successfully with new password!")

print("\n=== ALL AUTH TESTS PASSED PERFECTLY ===")
