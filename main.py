from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid
from openai import OpenAI
client = OpenAI()

app = FastAPI(
    title="UgandAPI Chat",
    description="This API facilitates communication for our chat-based mobile application hosted in Android Studio.",
    version="1.0.0"
)

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

chats = []
users = {}
tokens = {}

@app.get("/chats", response_model=List[ChatMessage])
def get_chats():
    return chats

@app.post("/chats", response_model=ChatMessage, status_code=201)
def post_chat(new_message: NewChatMessage):
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

@app.post("/users/login", response_model=TokenResponse)
def login(user_credentials: UserCredentials):
    if user_credentials.username in users and users[user_credentials.username]["password"] == user_credentials.password:
        token = str(uuid.uuid4())
        tokens[token] = user_credentials.username
        return {"token": token}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/users/register", response_model=UserResponse, status_code=201)
def register(user_registration: UserRegistration):
    if user_registration.username in users:
        raise HTTPException(status_code=400, detail="Username already taken")
    userId = str(uuid.uuid4())
    users[user_registration.username] = {
        "userId": userId,
        "password": user_registration.password,
        "email": user_registration.email
    }
    return {
        "userId": userId,
        "username": user_registration.username,
        "email": user_registration.email
    }

# uvicorn main:app --reload
