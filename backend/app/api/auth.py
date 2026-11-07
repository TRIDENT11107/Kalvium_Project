import smtplib
import uuid
from urllib.parse import quote
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from pwdlib import PasswordHash
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.schemas.api import Credentials, TokenOut, UserOut, ResetRequest, ResetConfirm
from app.security import hash_password,verify_password,make_token,current_user
from app.settings import settings
router=APIRouter(prefix="/api/auth",tags=["authentication"])
@router.post("/register",response_model=TokenOut,status_code=201)
def register(payload:Credentials,db:Session=Depends(get_db)):
    email=payload.email.lower()
    if db.query(User).filter_by(email=email).first(): raise HTTPException(409,"An account with this email already exists")
    user=User(email=email,password_hash=hash_password(payload.password)); db.add(user); db.commit(); db.refresh(user)
    return {"access_token":make_token(user),"user":user}
@router.post("/login",response_model=TokenOut)
def login(payload:Credentials,db:Session=Depends(get_db)):
    user=db.query(User).filter_by(email=payload.email.lower()).first()
    if not user or not verify_password(payload.password,user.password_hash): raise HTTPException(401,"Email or password is incorrect")
    return {"access_token":make_token(user),"user":user}
@router.get("/me",response_model=UserOut)
def me(user:User=Depends(current_user)): return user
@router.post("/password-reset/request")
def request_reset(payload:ResetRequest,db:Session=Depends(get_db)):
    user=db.query(User).filter_by(email=payload.email.lower()).first()
    if user and settings.smtp_host:
        reset_id=str(uuid.uuid4()); user.password_reset_jti=reset_id; db.commit()
        token=jwt.encode({"sub":str(user.id),"jti":reset_id,"purpose":"password_reset","exp":datetime.now(timezone.utc)+timedelta(minutes=20)},settings.jwt_secret,algorithm="HS256")
        msg=EmailMessage(); msg["Subject"]="AI Lesson Studio password reset"; msg["From"]=settings.smtp_from; msg["To"]=user.email
        msg.set_content("Use this one-time link to reset your password: "+settings.frontend_url.rstrip("/")+"/reset-password?token="+quote(token)+"\nIt expires in 20 minutes.")
        try:
            smtp_class=smtplib.SMTP_SSL if settings.smtp_port==465 else smtplib.SMTP
            with smtp_class(settings.smtp_host,settings.smtp_port,timeout=10) as server:
                if settings.smtp_port!=465: server.starttls()
                if settings.smtp_user: server.login(settings.smtp_user,settings.smtp_password)
                server.send_message(msg)
        except Exception: pass
    return {"message":"If this address belongs to an account and email delivery is configured, reset instructions will arrive shortly."}
@router.post("/password-reset/confirm")
def confirm_reset(payload:ResetConfirm,db:Session=Depends(get_db)):
    try:
        data=jwt.decode(payload.token,settings.jwt_secret,algorithms=["HS256"])
        if data.get("purpose")!="password_reset": raise ValueError()
        user=db.get(User,int(data["sub"]))
        if user is None or not data.get("jti") or user.password_reset_jti!=data["jti"]: user=None
    except (JWTError,ValueError,KeyError,TypeError): user=None
    if not user: raise HTTPException(400,"Reset token is invalid or expired")
    user.password_hash=hash_password(payload.password); user.password_reset_jti=None; db.commit(); return {"updated":True}
