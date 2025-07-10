# schema.py
import os
import bcrypt
import ollama
import fitz  # PyMuPDF
import torch
from torchvision import transforms
from PIL import Image
from app.models import db, User, ChatHistory
from app.style_transfer import run_style_transfer
from ariadne import (
    QueryType,
    MutationType,
    ScalarType,
    make_executable_schema
)

# ========
# Constants
# ========
MODEL_NAME = "my-chat"
MAX_PDF_SIZE = 5 * 1024 * 1024  # 5MB

UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Load your CNN style models once for efficiency
from app.transformer_net import TransformerNet  # Import your fast style transfer model

STYLE_MODELS = {
    "mosaic": "mosaic.pth",
    "candy": "candy.pth",
    "udnie": "udnie.pth"
    # Add more styles as needed
}

# ==========
# Type Definitions
# ==========
type_defs = """
    scalar Upload

    type Query {
        getUser(username: String!): User
    }

    type Mutation {
        register(username: String!, password: String!): RegisterResponse!
        login(username: String!, password: String!): LoginResponse!
        chat(username: String!, message: String!): ChatResponse!
        extractPDFText(file: Upload!): PDFExtractionResult!
        styleTransfer(file: Upload!, style: String!): StyleTransferResult!
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

    type PDFPage {
        page: Int!
        content: String!
        preview: String
    }

    type PDFExtractionResult {
        success: Boolean!
        filename: String!
        page_count: Int!
        pages: [PDFPage!]!
    }

    type StyleTransferResult {
        imageUrl: String!
        message: String
    }
    type ChatMessage {
        id: Int!
        role: String!
        content: String!
    }

    extend type Query {
        getChatHistory(username: String!): [ChatMessage!]!
    }

"""

# ==========
# Resolvers
# ==========
query = QueryType()
mutation = MutationType()
upload_scalar = ScalarType("Upload")

@query.field("getUser")
def resolve_get_user(_, info, username):
    return User.query.filter_by(username=username).first()

@mutation.field("register")
def resolve_register(_, info, username, password):
    if User.query.filter_by(username=username).first():
        return {"success": False, "message": "Username exists"}
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    new_user = User(username=username, password_hash=pw_hash)
    db.session.add(new_user)
    db.session.commit()
    return {"success": True, "message": "Registered!"}

@mutation.field("login")
def resolve_login(_, info, username, password):
    user = User.query.filter_by(username=username).first()
    if not user:
        return {"success": False, "message": "Login failed"}
    if bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        return {"success": True, "message": "Login successful"}
    return {"success": False, "message": "Login failed"}

@mutation.field("chat")
def resolve_chat(_, info, username, message):
    user = User.query.filter_by(username=username).first()
    if not user:
        return {"reply": "Invalid user"}

    # Tight context: last 2 messages
    history = ChatHistory.query.filter_by(user_id=user.id).order_by(ChatHistory.id.desc()).limit(2).all()
    messages = [{"role": "system", "content": "You are Tintu 🧸, a helpful bot."}]
    messages += [{"role": h.role, "content": h.content} for h in reversed(history)]
    messages.append({"role": "user", "content": message})

    try:
        stream = ollama.chat(
            model=MODEL_NAME,
            messages=messages,
            stream=True,
            options={
                "num_predict": 200,
                "temperature": 0.7
            }
        )

        chunks = []
        for chunk in stream:
            chunks.append(chunk['message']['content'])
        bot_reply = "".join(chunks)

    except Exception as e:
        print(f"Ollama stream error: {e}")
        bot_reply = "Sorry, something went wrong while generating a reply."

    db.session.add(ChatHistory(user_id=user.id, role="user", content=message))
    db.session.add(ChatHistory(user_id=user.id, role="assistant", content=bot_reply))
    db.session.commit()

    return {"reply": bot_reply}

@mutation.field("extractPDFText")
def resolve_extract_pdf_text(_, info, file):
    file_obj = file
    filename = file_obj.filename

    if not filename.lower().endswith(".pdf"):
        return {"success": False, "filename": filename, "page_count": 0, "pages": []}

    file_obj.seek(0, os.SEEK_END)
    size = file_obj.tell()
    file_obj.seek(0)

    if size > MAX_PDF_SIZE:
        return {"success": False, "filename": filename, "page_count": 0, "pages": []}

    try:
        pdf_bytes = file_obj.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return {"success": False, "filename": filename, "page_count": 0, "pages": []}

    pages = []
    for i, page in enumerate(doc, start=1):
        content = page.get_text().strip()
        pages.append({
            "page": i,
            "content": content,
            "preview": content[:100]
        })
    doc.close()

    return {
        "success": True,
        "filename": filename,
        "page_count": len(pages),
        "pages": pages
    }

# ==========
# CNN Style Transfer Resolver
# ==========
@mutation.field("styleTransfer")
def resolve_style_transfer(_, info, file, style):
    file_obj = file
    filename = file_obj.filename

    # Save uploaded file
    input_path = os.path.join(UPLOAD_DIR, filename)
    file_obj.seek(0)
    with open(input_path, "wb") as f:
        f.write(file_obj.read())

    # Output path
    output_filename = f"stylized_{style}_{filename}"
    output_path = os.path.join(UPLOAD_DIR, output_filename)

    # Call reusable helper
    try:
        run_style_transfer(input_path, output_path, style)
        image_url = f"/uploads/{output_filename}"
        message = f"Your image is stylized with {style}!"
    except Exception as e:
        image_url = ""
        message = f"Style transfer failed: {e}"

    return {"imageUrl": image_url, "message": message}

@query.field("getChatHistory")
def resolve_get_chat_history(_, info, username):
    user = User.query.filter_by(username=username).first()
    if not user:
        return []
    history = ChatHistory.query.filter_by(user_id=user.id).order_by(ChatHistory.id.asc()).all()
    return [{"id": h.id, "role": h.role, "content": h.content} for h in history]


# ==========
# Schema
# ==========
schema = make_executable_schema(type_defs, [query, mutation, upload_scalar])
