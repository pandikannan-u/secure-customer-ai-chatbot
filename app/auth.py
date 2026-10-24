
import secrets
import hashlib
import time
from datetime import datetime, timedelta, timezone
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from jose import jwt

from app.config import settings
from app.database import get_db
from app.models import Customer

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Demo-only in-memory OTP storage.
# Production-la persistent storage and SMS provider use pannanum.
_otp_store = {}


class RequestOTP(BaseModel):
    mobile: str = Field(min_length=10, max_length=20)


class VerifyOTP(BaseModel):
    mobile: str = Field(min_length=10, max_length=20)
    otp: str = Field(pattern=r"^\d{6}$")


def normalize_mobile(mobile: str) -> str:
    return "".join(ch for ch in mobile if ch.isdigit())


@router.post("/request-otp")
def request_otp(payload: RequestOTP):
    mobile = normalize_mobile(payload.mobile)

    if len(mobile) < 10 or len(mobile) > 15:
        raise HTTPException(
            status_code=400,
            detail="Invalid mobile number",
        )

    now = time.time()
    existing = _otp_store.get(mobile)

    if existing and now - existing["sent_at"] < settings.OTP_RESEND_COOLDOWN_SECONDS:
        raise HTTPException(
            status_code=429,
            detail="Please wait 60 seconds before requesting another OTP",
        )

    otp = f"{secrets.randbelow(1_000_000):06d}"

    _otp_store[mobile] = {
        "hash": hashlib.sha256(otp.encode()).hexdigest(),
        "expires_at": now + settings.OTP_EXPIRE_MINUTES * 60,
        "sent_at": now,
        "attempts": 0,
    }

    # Internship demo only: OTP is returned for local testing.
    # Real applications must send OTP through a verified SMS provider.
    return {
        "message": "OTP generated for demo",
        "demo_otp": otp,
    }


@router.post("/verify-otp")
def verify_otp(
    payload: VerifyOTP,
    db: Session = Depends(get_db),
):
    mobile = normalize_mobile(payload.mobile)
    record = _otp_store.get(mobile)

    if not record:
        raise HTTPException(
            status_code=400,
            detail="Request an OTP first",
        )

    if time.time() > record["expires_at"]:
        _otp_store.pop(mobile, None)
        raise HTTPException(
            status_code=400,
            detail="OTP expired",
        )

    if record["attempts"] >= settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Request a new OTP after the cooldown.",
        )
    submitted_hash = hashlib.sha256(payload.otp.encode()).hexdigest()

    if not secrets.compare_digest(submitted_hash, record["hash"]):
        record["attempts"] += 1
        raise HTTPException(
            status_code=400,
            detail="Invalid OTP",
        )

    # OTP is single-use.
    _otp_store.pop(mobile, None)

    customer = (
        db.query(Customer)
        .filter(Customer.mobile == mobile)
        .first()
    )

    if not customer:
        raise HTTPException(
            status_code=403,
            detail="Customer not registered",
        )

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    token = jwt.encode(
        {
            "sub": str(customer.id),
            "exp": expire,
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    return {
        "message": "OTP verified",
        "customer_id": customer.id,
        "access_token": token,
        "token_type": "bearer",
    }

security = HTTPBearer()


def get_current_customer(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        customer_id = int(payload["sub"])
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    customer = db.query(Customer).filter(
        Customer.id == customer_id
    ).first()

    if not customer:
        raise HTTPException(
            status_code=401,
            detail="Customer not found",
        )

    return customer