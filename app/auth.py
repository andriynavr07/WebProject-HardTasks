from datetime import timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User, utcnow


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def set_login_cookie(response: Response, user_id: int) -> None:
    exp = utcnow() + timedelta(hours=settings.token_ttl_hours)
    token = jwt.encode({"sub": str(user_id), "exp": exp}, settings.secret_key, algorithm="HS256")
    response.set_cookie("token", token, httponly=True, samesite="lax", secure=settings.cookie_secure,
                        max_age=settings.token_ttl_hours * 3600)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("token")
    if not token:
        raise HTTPException(401, "Потрібна авторизація")
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user = db.get(User, int(data["sub"]))
    except Exception:
        raise HTTPException(401, "Недійсний токен")
    if user is None:
        raise HTTPException(401, "Користувача не знайдено")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Тільки для адміністратора")
    return user
