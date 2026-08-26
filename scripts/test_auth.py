import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(PROJECT_ROOT, "scripts"))

import auth

def test_auth():
    print("🔒 Testing PermTrack Authentication System...")

    # 1. Test user authentication with default accounts
    admin_user = auth.authenticate_user("admin", "PermTrack@2026")
    assert admin_user is not None, "Failed to authenticate default admin user"
    assert admin_user["username"] == "admin"
    print("   ✅ Admin authentication verified")

    rajdeep_user = auth.authenticate_user("rajdeep", "PermTrack@2026")
    assert rajdeep_user is not None, "Failed to authenticate rajdeep user"
    assert rajdeep_user["username"] == "rajdeep"
    print("   ✅ Rajdeep account authentication verified")

    # 2. Test invalid password
    invalid_user = auth.authenticate_user("admin", "WrongPassword")
    assert invalid_user is None, "Invalid password should fail"
    print("   ✅ Invalid password rejected")

    # 3. Test unknown user
    unknown_user = auth.authenticate_user("random_stranger", "PermTrack@2026")
    assert unknown_user is None, "Unknown user should fail"
    print("   ✅ Unknown user rejected")

    # 4. Test session token creation and verification
    token = auth.create_session_token("rajdeep", remember_me=True)
    assert token and "." in token, "Token generation failed"
    
    verified = auth.verify_session_token(token)
    assert verified is not None, "Token verification failed"
    assert verified["username"] == "rajdeep"
    print("   ✅ Session token generation & HMAC-SHA256 signature verified")

    # 5. Test tampered token
    tampered_token = token[:-4] + "abcd"
    tampered_verified = auth.verify_session_token(tampered_token)
    assert tampered_verified is None, "Tampered token should be rejected"
    print("   ✅ Tampered token signature rejected")

    print("\n🎉 ALL AUTHENTICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_auth()
