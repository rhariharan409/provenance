import uuid
from datetime import timedelta
import pytest
import jwt
from app.security import create_session_token, verify_session_token


def test_session_jwt_round_trip():
    user_id = uuid.uuid4()
    token = create_session_token(user_id)
    assert isinstance(token, str)

    verified_id = verify_session_token(token)
    assert verified_id == str(user_id)


def test_session_jwt_expired_rejected():
    user_id = uuid.uuid4()
    expired_token = create_session_token(user_id, expires_delta=timedelta(seconds=-10))

    with pytest.raises(jwt.PyJWTError):
        verify_session_token(expired_token)


def test_session_jwt_tampered_rejected():
    user_id = uuid.uuid4()
    token = create_session_token(user_id)

    # Tamper with token by replacing the last 4 characters
    tampered = token[:-4] + ("xxxx" if token[-4:] != "xxxx" else "yyyy")
    with pytest.raises(jwt.PyJWTError):
        verify_session_token(tampered)
