from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from pwdlib import PasswordHash
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.settings import settings
from app.database import get_db
from app.models import User
hasher=PasswordHash.recommended()
bearer=HTTPBearer(auto_error=False)
def hash_password(password:str)->str: return hasher.hash(password)
def verify_password(password:str,hashed:str)->bool: return hasher.verify(password,hashed)
def make_token(user:User):
    exp=datetime.now(timezone.utc)+timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub":str(user.id),"exp":exp},settings.jwt_secret,algorithm="HS256")
def current_user(credentials:HTTPAuthorizationCredentials|None=Depends(bearer),db:Session=Depends(get_db))->User:
    if credentials is None: raise HTTPException(401,"Not authenticated",headers={"WWW-Authenticate":"Bearer"})
    try:
        payload=jwt.decode(credentials.credentials,settings.jwt_secret,algorithms=["HS256"]); uid=int(payload["sub"])
    except (JWTError,ValueError,KeyError): raise HTTPException(401,"Invalid or expired access token",headers={"WWW-Authenticate":"Bearer"})
    user=db.get(User,uid)
    if not user: raise HTTPException(401,"User no longer exists")
    return user
def owned_lesson(lesson_id:int,db:Session,user:User)->object:
    from app.models import Lesson
    lesson=db.get(Lesson,lesson_id)
    if not lesson or lesson.owner_id!=user.id: raise HTTPException(404,"Lesson not found")
    return lesson
