from typing import Dict, List, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer,OAuth2PasswordRequestForm
from pydantic import BaseModel
import uvicorn
import json
from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.fastapi import register_tortoise
from tortoise.contrib.pydantic import pydantic_model_creator
from passlib.hash import bcrypt
import jwt
import sqlalchemy.orm as _orm
import services as _services, schemas as _schemas


DEBUG = False

JWT_SECRET = 'myjwtsecret'
app = FastAPI()

_services.create_database()

class User(Model):
    id = fields.IntField(pk=True)
    username = fields.CharField(50, unique=True)
    password_hash = fields.CharField(128)

    def verify_password(self, password):
        return bcrypt.verify(password, self.password_hash)


User_Pydantic = pydantic_model_creator(User, name='User')
UserIn_Pydantic = pydantic_model_creator(User, name='UserIn', exclude_readonly=True)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def authenticate_user(username: str, password: str, db: _orm.Session = Depends(_services.get_db)):
    # user = await User.get(username=username)
    user = _services.get_user_by_username(db=db, username=username)
    if not user:
        return False
    if not _services.verify_password(db, username,password):
        return False
    # print('Working')
    return user

@app.post('/api/token', tags=["User"])
async def generate_token(form_data: OAuth2PasswordRequestForm= Depends(),  db: _orm.Session = Depends(_services.get_db)):
    user = await authenticate_user(form_data.username, form_data.password, db=db)
    print(user.__dict__)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail = 'Invalid Username or Password')
    # user_obj = await User_Pydantic.from_tortoise_orm(user)
    data = {
        'username' : user.username,
        'password_hash' : user.password_hash
    }
    token = jwt.encode(data, JWT_SECRET)
    return {'access_token' : token, 'token_type': 'bearer'}


@app.post("/users/", response_model=_schemas.User)
async def create_user(user: _schemas.UserCreate, db: _orm.Session = Depends(_services.get_db)):
    db_user =  _services.get_user_by_username(db=db, username=user.username)
    if db_user:
        raise HTTPException(
            status_code=400, detail="Username which is already in use."
        )
    return _services.create_user(db=db, user=user)


async def get_token(token: str = Depends(oauth2_scheme),  db: _orm.Session = Depends(_services.get_db)):
    try:
        print("get_token")
        payload = jwt.decode(token , JWT_SECRET, algorithms=['HS256'])
        # user = await User.get(id=payload.get('id'))
        username = payload.get('username')
        print(f'username {username}')
        user = _services.get_user_by_username(db=db,username=payload.get('username'))
        # user: str = payload.get("username")
        # print(f'username {user}')
    except:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail = 'Invalid Username or Password')
    return user

@app.post("/items/")
async def get(str, token: str = Depends(oauth2_scheme), db: _orm.Session = Depends(_services.get_db)):
    user = await get_token(token, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    return 'Hello world'

if not DEBUG:
    if __name__ == "__main__":
        uvicorn.run(app, host="localhost",port=8000)