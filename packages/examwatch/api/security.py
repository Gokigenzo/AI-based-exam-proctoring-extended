import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from .models import Device, Member


DEMO_USER = "00000000-0000-4000-8000-000000000001"
DEMO_ROOM = "00000000-0000-4000-8000-000000000002"
DEMO_DEVICE = "00000000-0000-4000-8000-000000000003"


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class Principal:
    user_id: str | None = None
    device_id: str | None = None
    room_id: str | None = None


def authenticate(token, db, config):
    if config.env != "production" and config.demo_token and hmac.compare_digest(token, config.demo_token):
        return Principal(user_id=DEMO_USER)
    device = db.scalar(select(Device).where(Device.token_hash == digest(token), Device.revoked.is_(False)))
    if device:
        return Principal(device_id=device.id, room_id=device.room_id)
    if not config.supabase_url:
        raise HTTPException(401, "Thông tin đăng nhập không hợp lệ")
    try:
        response = httpx.get(f"{config.supabase_url}/auth/v1/user", headers={"apikey": config.supabase_key, "Authorization": f"Bearer {token}"}, timeout=10)
        if response.status_code != 200:
            raise HTTPException(401, "Phiên đăng nhập không hợp lệ")
        user = response.json()
        if user.get("is_anonymous") or not user.get("id"):
            raise HTTPException(401, "Yêu cầu tài khoản giám thị")
        return Principal(user_id=user["id"])
    except httpx.RequestError:
        raise HTTPException(503, "Không xác thực được với Supabase") from None


def require_room(db, actor, room_id, admin=False):
    if actor.device_id:
        if admin or actor.room_id != room_id:
            raise HTTPException(403, "Thiết bị không có quyền")
        return
    member = db.get(Member, (room_id, actor.user_id))
    if not member or (admin and member.role != "admin"):
        raise HTTPException(403, "Bạn không có quyền truy cập phòng thi")


def capability(secret, asset_id, action, expires):
    message = f"{asset_id}:{action}:{expires}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def check_capability(secret, asset_id, action, expires, signature):
    if expires < time.time() or not hmac.compare_digest(capability(secret, asset_id, action, expires), signature):
        raise HTTPException(403, "Liên kết đã hết hạn hoặc không hợp lệ")


def new_device_token():
    return "ew_" + secrets.token_urlsafe(40)
