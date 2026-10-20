from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user, hash_password, set_login_cookie, verify_password
from ..db import get_db
from ..models import User
from ..schemas import Credentials

router = APIRouter(prefix="/api")


@router.post("/register")
def register(body: Credentials, response: Response, db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(409, "Користувач вже існує")
    user = User(username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    set_login_cookie(response, user.id)
    return {"username": user.username, "is_admin": False}


@router.post("/login")
def login(body: Credentials, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Невірний логін або пароль")
    set_login_cookie(response, user.id)
    return {"username": user.username, "is_admin": user.is_admin}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("token")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username, "is_admin": user.is_admin}
