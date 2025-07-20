from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_migrate import Migrate  
from flask_cors import CORS
from app.models import db, User, ChatHistory
from app.pdf_upload import pdf_bp
from app.pinecone_client import semantic_search
from app.embedding_helper import embed_text
import json
import ollama
import os
from ariadne import graphql_sync
from app.constants import PLAYGROUND_HTML
from app.schema import schema
from ariadne.file_uploads import combine_multipart_data

MODEL_NAME = "my-chat"
UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

my_app = Flask(__name__)
CORS(my_app)

#  Configure DB before initializing db & migrate
my_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
my_app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {"check_same_thread": False}
}

#  Proper init order
db.init_app(my_app)
migrate = Migrate(my_app, db)

#  Register other routes/blueprints
my_app.register_blueprint(pdf_bp)

# Optional: Create tables if db is fresh (useful before first migration)
with my_app.app_context():
    db.create_all()

# [Your existing routes remain unchanged, no need to modify the stream_chat code again]

if __name__ == "__main__":
    my_app.run(debug=True, threaded=True)  # Enable threaded=True


@my_app.route("/")
def index():
    return "✅ Hello, your Flask dev server is running!"

@my_app.route("/graphql", methods=["GET"])
def graphql_playground():
    return PLAYGROUND_HTML, 200

@my_app.route("/graphql", methods=["POST"])
def graphql_server():
    if request.content_type.startswith("multipart/form-data"):
        operations = json.loads(request.form.get("operations"))
        file_map = json.loads(request.form.get("map"))
        files = dict(request.files)
        data = combine_multipart_data(operations, file_map, files)
    else:
        data = request.get_json()

    success, result = graphql_sync(schema, data, context_value=request, debug=True)
    status_code = 200 if success else 400
    return jsonify(result), status_code

@my_app.route("/stream-chat", methods=["POST"])
def stream_chat():
    data = request.get_json()
    username = data.get("username")
    user_input = data.get("message", "").strip()

    if not username or not user_input:
        def error_gen():
            yield "data: Invalid input\n\n"
        return Response(error_gen(), mimetype="text/event-stream")

    user = User.query.filter_by(username=username).first()
    if not user:
        def error_gen():
            yield "data: Invalid user\n\n"
        return Response(error_gen(), mimetype="text/event-stream")

    # Load chat history and run semantic search _within context_
    history = ChatHistory.query.filter_by(user_id=user.id).order_by(ChatHistory.id.desc()).limit(5).all()
    messages = [{"role": "system", "content": "You are Tintu 🧸, a helpful bot with document memory."}]
    messages += [{"role": h.role, "content": h.content} for h in reversed(history)]

    try:
        query_embedding = embed_text(user_input)
        results = semantic_search(query_embedding, top_k=5, namespace=username)
        context_chunks = [
            match['metadata'].get('chunk')
            for match in results.get("matches", [])
            if 'chunk' in match.get("metadata", {})
        ]
        context = "\n".join(context_chunks)

        if len(context.split()) > 750:
            summary = ollama.chat(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": "Summarize the following document memory to help answer a question."},
                    {"role": "user", "content": context}
                ],
                stream=False,
                options={"temperature": 0.5}
            )["message"]["content"]
            messages.append({"role": "system", "content": "Relevant summarized memory:\n" + summary})
        elif context:
            messages.append({"role": "system", "content": "Relevant context:\n" + context})
    except Exception as search_error:
        def search_error_gen():
            yield f"data: Error during semantic search: {str(search_error)}\n\n"
        return Response(search_error_gen(), mimetype="text/event-stream")

    # Prepare for generation
    messages.append({"role": "user", "content": user_input})

    @stream_with_context
    def generate():
        full_reply = ""
        try:
            stream = ollama.chat(
                model=MODEL_NAME,
                messages=messages,
                stream=True,
                options={"temperature": 0.7, "num_predict": 4096}
            )
            print(type(stream))
            print(stream)
            for chunk in stream:
                token = chunk.get("message", {}).get("content")
                if token:
                    full_reply += token
                    yield f"data: {json.dumps({'token': token})}\n\n"

        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"

        finally:
            try:
                db.session.add(ChatHistory(user_id=user.id, role="user", content=user_input))
                db.session.add(ChatHistory(user_id=user.id, role="assistant", content=full_reply))
                db.session.commit()
            except Exception as db_error:
                db.session.rollback()
                yield f"data: Error saving chat: {str(db_error)}\n\n"

            yield "data: [DONE]\n\n"

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Access-Control-Allow-Origin": "*"
    }

    return Response(generate(), headers=headers)



# ✅ NEW: Serve stylized images from /uploads/
@my_app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

if __name__ == "__main__":
    my_app.run(debug=True, threaded=True)
