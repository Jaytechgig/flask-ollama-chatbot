# schema.py
import os
import bcrypt
import ollama
import fitz  # PyMuPDF
import torch
import logging
from datetime import datetime
from torchvision import transforms
from PIL import Image

from app.models import db, User, ChatHistory
from app.style_transfer import run_style_transfer
from app.embedding_helper import embed_text
from app.pinecone_client import semantic_search
from app.transformer_net import TransformerNet

from ariadne import (
    QueryType,
    MutationType,
    ScalarType,
    make_executable_schema
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MODEL_NAME = "my-chat"
MAX_PDF_SIZE = 5 * 1024 * 1024
UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

STYLE_MODELS = {
    "mosaic": "mosaic.pth",
    "candy": "candy.pth",
    "udnie": "udnie.pth"
}

type_defs = """
    scalar Upload
    scalar DateTime

    type Query {
        getUser(username: String!): User
        semanticSearch(query: String!, username: String!): [SemanticSearchResult!]!
        getChatHistory(username: String!): [ChatMessage!]!
    }

    type Mutation {
        register(username: String!, password: String!): RegisterResponse!
        login(username: String!, password: String!): LoginResponse!
        chat(username: String!, message: String!): ChatResponse!
        chat_update(user_id: Int!, chat_id: String!): ChatUpdateResponse!
        extractPDFText(username: String!, file: Upload!): PDFExtractionResult!
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
        user_id: Int
    }

    type ChatResponse {
        reply: String!
    }

    type ChatUpdateResponse {
        success: Boolean!
        message: String!
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
        created_at: DateTime
        updated_at: DateTime
    }

    type SemanticSearchResult {
        id: String!
        filename: String!
        page: Int!
        content: String
        score: Float!
    }
"""

query = QueryType()
mutation = MutationType()
upload_scalar = ScalarType("Upload")
datetime_scalar = ScalarType("DateTime")

@datetime_scalar.serializer
def serialize_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value

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
        return {
            "success": True,
            "message": "Login successful",
            "user_id": user.id  # ✅ field name matches schema
        }
    return {"success": False, "message": "Login failed"}


@mutation.field("chat")
def resolve_chat(_, info, username, message):
    user = User.query.filter_by(username=username).first()
    if not user:
        return {"reply": "Invalid user"}

    history = ChatHistory.query.filter_by(user_id=user.id).order_by(ChatHistory.id.desc()).limit(2).all()
    messages = [{"role": "system", "content": "You are Tintu \U0001F9F8, a helpful bot."}]
    messages += [{"role": h.role, "content": h.content} for h in reversed(history)]
    messages.append({"role": "user", "content": message})

    try:
        stream = ollama.chat(
            model=MODEL_NAME,
            messages=messages,
            stream=True,
            options={"num_predict": 200, "temperature": 0.7}
        )
        chunks = [chunk['message']['content'] for chunk in stream]
        bot_reply = "".join(chunks)
    except Exception as e:
        print(f"Ollama stream error: {e}")
        bot_reply = "Sorry, something went wrong."

    db.session.add(ChatHistory(user_id=user.id, role="user", content=message))
    db.session.add(ChatHistory(user_id=user.id, role="assistant", content=bot_reply))
    db.session.commit()

    return {"reply": bot_reply}

@mutation.field("chat_update")
def resolve_chat(_, info, user_id, chat_id):
    try:
        chats_to_update = ChatHistory.query.filter_by(user_id=user_id)
        chats_to_update = chats_to_update.filter(ChatHistory.chat_id.is_(None)).all()
        if not chats_to_update:
            return {"success": False, "message": "No chats with null chat_id found."}

        for chat in chats_to_update:
            chat.chat_id = chat_id
        db.session.commit()
        return {"success": True, "message": f"Updated {len(chats_to_update)} chat(s)."}
    except Exception as e:
        db.session.rollback()
        return {"success": False, "message": f"Error: {str(e)}"}

@mutation.field("extractPDFText")
def resolve_extract_pdf_text(_, info, username, file):
    import fitz
    from app.pinecone_client import upsert_vectors
    from app.embedding_helper import embed_text

    filename = file.filename
    file.seek(0, os.SEEK_END)
    if file.tell() > MAX_PDF_SIZE:
        return {"success": False, "filename": filename, "page_count": 0, "pages": []}
    file.seek(0)

    try:
        pdf_bytes = file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        return {"success": False, "filename": filename, "page_count": 0, "pages": []}

    pages, vectors = [], []
    for i, page in enumerate(doc, start=1):
        text = page.get_text().strip()
        if not text:
            continue
        pages.append({"page": i, "content": text, "preview": text[:100]})
        embedding = embed_text(text)
        vectors.append((f"{filename}-page-{i}", embedding, {"filename": filename, "page": i, "content": text}))

    doc.close()
    if vectors:
        upsert_vectors(vectors, namespace=username)

    return {"success": True, "filename": filename, "page_count": len(pages), "pages": pages}

@query.field("semanticSearch")
def resolve_semantic_search(_, info, username, query):
    query_embedding = embed_text(query)
    results = semantic_search(query_embedding=query_embedding, top_k=5, namespace=username)
    semantic_results = []
    for match in results.get("matches", []):
        metadata = match.get("metadata", {})
        semantic_results.append({
            "id": match.get("id"),
            "filename": metadata.get("filename", ""),
            "page": metadata.get("page", 0),
            "content": metadata.get("content", ""),
            "score": match.get("score", 0)
        })
    return semantic_results

@query.field("getChatHistory")
def resolve_get_chat_history(_, info, username):
    user = User.query.filter_by(username=username).first()
    if not user:
        return []
    history = ChatHistory.query.filter_by(user_id=user.id).order_by(ChatHistory.id.asc()).all()
    return [{"id": h.id, "role": h.role, "content": h.content, "created_at": h.created_at, "updated_at": h.updated_at} for h in history]

@mutation.field("styleTransfer")
def resolve_style_transfer(_, info, file, style):
    input_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(input_path, "wb") as f:
        f.write(file.read())
    output_filename = f"stylized_{style}_{file.filename}"
    output_path = os.path.join(UPLOAD_DIR, output_filename)
    try:
        run_style_transfer(input_path, output_path, style)
        return {"imageUrl": f"/uploads/{output_filename}", "message": f"Styled with {style}"}
    except Exception as e:
        return {"imageUrl": "", "message": f"Failed: {e}"}

schema = make_executable_schema(type_defs, [query, mutation, upload_scalar, datetime_scalar])
