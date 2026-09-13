from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from database import SessionLocal
from datetime import timedelta ,datetime, timezone
from models import Users
import models
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from jose import jwt, JWTError

router = APIRouter()
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
OAuth2_bearer = OAuth2PasswordBearer(tokenUrl="login")

SECRET_KEY = "gy4RbvpY1aT5dm3zAtFRXP7pTNX9a12V"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]



class CreateUser(BaseModel):
    email: str
    username: str
    first_name: str
    last_name: str
    hash_password: str
    role: str



class UpdateUser(BaseModel):
    email: Optional[str] = Field(default=None)
    username: Optional[str] = Field(default=None)
    first_name: Optional[str] = Field(default=None)
    last_name: Optional[str] = Field(default=None)
  

class UpdatePassword(BaseModel):
    current_password: str
    new_password: str
   


def authenticate_user(db: Session, username: str, password: str):
    user = db.query(Users).filter(Users.username == username).first()
    if not user:
        return False
    if not bcrypt_context.verify(password, user.hash_password):
        return False
    return user

def create_access_token(username:str, user_id:int,role:str,expires_delta: timedelta):
    encode = {"sub": username, "id": user_id,'role': role}
    expire = datetime.now(timezone.utc) + expires_delta
    encode.update({"exp": expire})
    token = jwt.encode(encode, SECRET_KEY, algorithm=ALGORITHM)
    return token


def get_current_user(token: Annotated[str, Depends(OAuth2_bearer)]):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: int = payload.get("id")
        role: str = payload.get("role")
        if username is None or user_id is None:
           raise HTTPException(status_code=404, detail="User not found")
        return {"username": username, "id": user_id, "role": role}
    except JWTError:
        raise HTTPException(status_code=404, detail="Invalid token")


user_dependency = Annotated[dict, Depends(get_current_user)]

@router.post("/createuser/")
def create_users(db: db_dependency, new_user: CreateUser):
    user_model = Users(
        email=new_user.email,
        username=new_user.username, 
        first_name=new_user.first_name,
        last_name=new_user.last_name,
        hash_password=bcrypt_context.hash(new_user.hash_password),
        is_active=True,
        role=new_user.role,
    )
    db.add(user_model)
    db.commit()

    return JSONResponse(content={"message": "User created successfully"}, status_code=201)


@router.post("/login/")
def login_user(db: db_dependency, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        return JSONResponse(content={"message": "Failed to authenticate user"}, status_code=401)
    access_token = create_access_token(user.username, user.id, user.role, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return JSONResponse(content={"access_token": access_token, "token_type": "bearer"}, status_code=200)


@router.put("/edituser")
def update_user(user: user_dependency, db: db_dependency, update_user: UpdateUser):
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user_model = db.query(models.Users).filter(models.Users.id == user.get("id")).first()
    if user_model is None:
        raise HTTPException(status_code=404, detail="User not found")
    update_data = update_user.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user_model, key, value)
    db.commit()
    return JSONResponse(content={"message": "User updated successfully"}, status_code=200)



@router.put("/passwordchange")
def update_password(user: user_dependency, db: db_dependency, update_password: UpdatePassword):
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user_model = db.query(models.Users).filter(models.Users.id == user.get("id")).first()
    if user_model is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not bcrypt_context.verify(update_password.current_password, user_model.hash_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user_model.hash_password = bcrypt_context.hash(update_password.new_password)
    db.commit()
    return JSONResponse(content={"message": "Password updated successfully"}, status_code=200)


@router.get('/user')
def get_user_details(user: user_dependency, db: db_dependency):
    if user is None:
        raise HTTPException(status_code=401, detail='Failed Authentication')
    
    current_user = db.query(Users).filter(Users.id == user.get('id')).first()
    if current_user is None:
        raise HTTPException(status_code=404, detail='User not found')
    
    return {
        'id': current_user.id,
        'email': current_user.email,
        'username': current_user.username,
        'firstname': current_user.firstname,
        'lastname': current_user.lastname,
        'role': current_user.role,
        'is_active': current_user.is_active
    }