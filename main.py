from typing import List, Optional

from openai import OpenAI
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from datetime import datetime
import uuid
import jwt
import sqlalchemy.orm as _orm
import services as _services, schemas as _schemas
from tortoise.models import Model
from tortoise import fields
from passlib.hash import bcrypt
from tortoise.contrib.pydantic import pydantic_model_creator


# Define a simple secret key for JWT encoding
JWT_SECRET = 'myjwtsecret'
client = OpenAI()

# Initialize FastAPI
app = FastAPI(
    title="UgandAPI Chat",
    description="This API facilitates communication for our chat-based mobile application hosted in Android Studio.",
    version="1.0.0"
)

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


# Models
class ChatMessage(BaseModel):
    messageId: str
    sender: str
    content: str
    timestamp: datetime

class NewChatMessage(BaseModel):
    sender: str
    content: str

class UserCredentials(BaseModel):
    username: str
    password: str

class UserRegistration(BaseModel):
    username: str
    password: str
    email: str

class UserResponse(BaseModel):
    userId: str
    username: str
    email: str

class TokenResponse(BaseModel):
    token: str

# In-memory storage for simplicity
chats = []
tokens = {}

# Authentication and Token Management
async def authenticate_user(username: str, password: str, db: _orm.Session = Depends(_services.get_db)):
    user = _services.get_user_by_username(db=db, username=username)
    if not user or not _services.verify_password(db, username, password):
        return None
    return user

@app.post('/api/token', tags=["User"])
async def generate_token(form_data: OAuth2PasswordRequestForm= Depends(),  db: _orm.Session = Depends(_services.get_db)):
    user = await authenticate_user(form_data.username, form_data.password, db=db)
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


# User Registration
@app.post("/users/register", response_model=_schemas.User)
async def create_user(user: _schemas.UserCreate, db: _orm.Session = Depends(_services.get_db)):
    db_user =  _services.get_user_by_username(db=db, username=user.username)
    if db_user:
        raise HTTPException(
            status_code=400, detail="Username which is already in use."
        )
    return _services.create_user(db=db, user=user)

# Chat Endpoints
@app.get("/chats", response_model=List[ChatMessage])
def get_chats():
    return chats

@app.post("/chats", response_model=ChatMessage, status_code=201)
def post_chat(new_message: NewChatMessage, token: str = Depends(oauth2_scheme), db: _orm.Session = Depends(_services.get_db)):
    #authentication
    user = get_token(token, db)    
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    #chatgpt
    completion = client.chat.completions.create(
    model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "- Your goal is to provide the user information about how to plant their farm in Uganda"},
            {"role": "user", "content": new_message.content}
        ]
    )
    message = ChatMessage(
        messageId=str(uuid.uuid4()),
        sender=new_message.sender,
        content= str(completion.choices[0].message),
        timestamp=datetime.utcnow()
    
    )    
    return message

@app.get("/chats/{messageId}", response_model=ChatMessage)
def get_chat(messageId: str):
    for chat in chats:
        if chat.messageId == messageId:
            return chat
    raise HTTPException(status_code=404, detail="Message not found")

# Items Endpoint (Example secured endpoint)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

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
async def get_items(str: Optional[str], token: str = Depends(oauth2_scheme), db: _orm.Session = Depends(_services.get_db)):
    user = await get_token(token, db)    
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    #this is where our app comes in
    return 'Hello world'

# Run the app
if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000)

# uvicorn main:app --reload
