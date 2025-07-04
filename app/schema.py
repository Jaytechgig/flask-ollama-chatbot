# schema.py

import bcrypt
import ollama
from ariadne import QueryType, MutationType, make_executable_schema
from models import db, User, ChatHistory

MODEL_NAME = "my-chat"

# ==================
# GraphQL type defs
# ==================
type_defs = """
    type Query {
        getUser(username: String!): User
    }

    type Mutation {
        register(username: String!, password: String!): RegisterResponse!
        login(username: String!, password: String!): LoginResponse!
        chat(username: String!, message: String!): ChatResponse!
    }

    type User {
        id: Int!
        username: String!
    }

    type RegisterResponse {
        success: Boolean!
        message: String!
    }

    type LoginResponse {
        success: Boolean!
        message: String!
    }

    type ChatResponse {
        reply: String!
    }
"""

# ==================
# Resolvers
# ==================
query = QueryType()
mutation = MutationType()

@query.field("getUser")
def resolve_get_user(_, info, username):
    user = User.query.filter_by(username=username).first()
    return user

@mutation.field("register")
def resolve_register(_, info, username, password):
    if User.query.filter_by(username=username).first():
        return {"success": False, "message": "Username exists"}
    pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    new_user = User(username=username, password_hash=pw_hash.decode('utf-8'))
    db.session.add(new_user)
    db.session.commit()
    return {"success": True, "message": "Registered!"}

@mutation.field("login")
def resolve_login(_, info, username, password):
    user = User.query.filter_by(username=username).first()
    if not user:
        return {"success": False, "message": "Invalid credentials"}
    if bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
        return {"success": True, "message": "Login successful"}
    else:
        return {"success": False, "message": "Invalid credentials"}

@mutation.field("chat")
def resolve_chat(_, info, username, message):
    user = User.query.filter_by(username=username).first()
    if not user:
        return {"reply": "Invalid user"}

    # Load recent history
    history = ChatHistory.query.filter_by(user_id=user.id).order_by(ChatHistory.id.desc()).limit(5).all()
    messages = [{"role": "system", "content": "You are Tintu 🧸, helpful bot."}]
    for h in reversed(history):
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": message})

    response = ollama.chat(model=MODEL_NAME, messages=messages)
    bot_reply = response["message"]["content"]

    # Save both
    db.session.add(ChatHistory(user_id=user.id, role="user", content=message))
    db.session.add(ChatHistory(user_id=user.id, role="assistant", content=bot_reply))
    db.session.commit()

    return {"reply": bot_reply}

schema = make_executable_schema(type_defs, query, mutation)
