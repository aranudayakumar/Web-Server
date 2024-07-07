import requests
import json
import time

base_url = "http://127.0.0.1:8000"

results = {}

response = requests.get(f"{base_url}/chats")
results["GET /chats"] = response.json()

new_message = {
    "sender": "user1",
    "content": "Hi there!"
}
response = requests.post(f"{base_url}/chats", data=json.dumps(new_message), headers={"Content-Type": "application/json"})
results["POST /chats"] = response.json()

time.sleep(1)

message_id = response.json().get("messageId")
if message_id:
    response = requests.get(f"{base_url}/chats/{message_id}")
    results[f"GET /chats/{message_id}"] = response.json()
else:
    results["GET /chats/{messageId}"] = {"error": "No message ID returned from POST /chats to test GET /chats/{messageId}"}

new_user = {
    "username": "user1",
    "password": "secretPassword",
    "email": "user1@example.com"
}
response = requests.post(f"{base_url}/users/register", data=json.dumps(new_user), headers={"Content-Type": "application/json"})
results["POST /users/register"] = response.json()

credentials = {
    "username": "user1",
    "password": "secretPassword"
}
response = requests.post(f"{base_url}/users/login", data=json.dumps(credentials), headers={"Content-Type": "application/json"})
results["POST /users/login"] = response.json()
    
print(json.dumps(results, indent=4))
