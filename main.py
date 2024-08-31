from typing import List, Optional
import os
from openai import OpenAI, AssistantEventHandler
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from datetime import datetime
import uuid
import jwt
import re
import sqlalchemy.orm as _orm
from dotenv import load_dotenv
import services as _services, schemas as _schemas
from tortoise.models import Model
from tortoise import fields
from passlib.hash import bcrypt
from tortoise.contrib.pydantic import pydantic_model_creator
from guardrails import Guard
from guardrails.hub import NSFWText
from guardrails.hub import RestrictToTopic


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
    thread_id: Optional[str] = None  # Make thread_id optional in the response

class NewChatMessage(BaseModel):
    sender: str
    content: str
    thread_id: Optional[str] = None  # Include thread_id in the request model

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
users = {}
tokens = {}

def interact_with_assistant(prompt, thread_id=None):
    assistant = "asst_gJkvVb6RSZj8BofmghLOnWVi"
    
     # If a thread already exists, use its ID; otherwise, create a new one
    try:
        with open("thread_id.txt", "r") as file:
            thread_id = file.read().strip()
    except FileNotFoundError:
        thread = client.beta.threads.create()
        thread_id = thread.id
        with open("thread_id.txt", "w") as file:
            file.write(thread_id)

    # Create a message before starting the stream
    message = client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=prompt
    )

    class EventHandler(AssistantEventHandler):
        def on_text_delta(self, delta, snapshot):
            cleaned_value = re.sub(r"【\d+:\d+†.*?】", "", delta.value)
            self.response.append(cleaned_value)

    handler = EventHandler()
    handler.response = []

    # Stream the response from the assistant
    with client.beta.threads.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant,
        event_handler=handler,
    ) as stream:
        stream.until_done()

    return "".join(handler.response), thread_id

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
    
    # Load verified users from environment variable
    verified_users = os.getenv("VERIFIED_USERS", "").split(",")
    verified_usernames = set(verified_users)
    print(f"Verified users loaded: {verified_usernames}")  # Debugging print
    
    # Check if the username is in the verified users list
    print(f"Attempting to register user: {user.username}")  # Debugging print

    if user.username not in verified_usernames:
        print(f"Username {user.username} is not verified.")  # Debugging print
        raise HTTPException(
            status_code=400, detail="Username is not verified for registration."
        )
    # Check if the username already exists in the database.
    
    
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
    
    
    #gaurdrails
    # Setup Guard with the validator
    guard = Guard().use_many(
    NSFWText(threshold=0.8, validation_method="sentence", on_fail="exception"),
    RestrictToTopic(
        valid_topics=[
            "uganda", "farm", "planting", "crops", 
            "plant", "buyanga", "mbale", "namutumbas"
        ],
        disable_classifier=True,
        disable_llm=False,
        on_fail="exception"
        ))
    try:
        # Test failing response
        guard.validate(new_message.content)
    except Exception as e:
        errorMessage = ChatMessage(
        messageId=str(uuid.uuid4()),
        sender=new_message.sender,
        content= str(e),
        timestamp=datetime.utcnow()
        )  
        return errorMessage
        
    
    # Interact with OpenAI assistant
    response_content, thread_id = interact_with_assistant(new_message.content, new_message.thread_id)

    # Create a response message
    message = ChatMessage(
        messageId=str(uuid.uuid4()),
        sender=new_message.sender,
        content=response_content,
        timestamp=datetime.utcnow(),
        thread_id=thread_id
    )

    # Return the response
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

# Function to interact with the assistant



# Run the app
if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000)
    



# uvicorn main:app --reload