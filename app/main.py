from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_migrate import Migrate
from flask_cors import CORS
from app.models import db, User, ChatHistory
from app.pdf_upload import pdf_bp
from app.pinecone_client import semantic_search
from app.embedding_helper import embed_text
import json
import os
import requests
from ariadne import graphql_sync
from app.constants import PLAYGROUND_HTML
from app.schema import schema
from ariadne.file_uploads import combine_multipart_data

OLLAMA_HOST = "http://127.0.0.1:11434"
MODEL_NAME = "my-chat"
UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

my_app = Flask(__name__)
CORS(my_app)

# Configure DB
my_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
my_app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {"check_same_thread": False}
}

db.init_app(my_app)
migrate = Migrate(my_app, db)
my_app.register_blueprint(pdf_bp)

with my_app.app_context():
    db.create_all()

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
    username = data["username"]
    user_input = data["message"]

    user = User.query.filter_by(username=username).first()
    if not user:
        def error_gen():
            yield "data: Invalid user\n\n"
        return Response(error_gen(), mimetype="text/event-stream")

    history = ChatHistory.query.filter_by(user_id=user.id).order_by(ChatHistory.id.desc()).limit(2).all()
    messages = [{"role": "system", "content": "You are Tintu 🧸, a helpful bot."}]
    messages += [{"role": h.role, "content": h.content} for h in reversed(history)]
    messages.append({"role": "user", "content": user_input})

    def generate():
        try:
            response = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": MODEL_NAME,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "num_predict": 200,
                        "temperature": 0.7
                    }
                },
                stream=True
            )

            full_reply = ""

            for line in response.iter_lines():
                if not line:
                    continue

                decoded = line.decode("utf-8")

                # Print for debugging
                print("📩 Ollama line:", decoded)

                if decoded.startswith("data: "):
                    json_str = decoded[6:]
                else:
                    json_str = decoded

                try:
                    chunk = json.loads(json_str)
                    token = chunk.get("message", {}).get("content", "")
                    full_reply += token
                    yield f"data: {json.dumps({'token': token})}\n\n"
                except json.JSONDecodeError:
                    print("⚠️ Failed to decode:", json_str)
                    continue

            db.session.add(ChatHistory(user_id=user.id, role="user", content=user_input))
            db.session.add(ChatHistory(user_id=user.id, role="assistant", content=full_reply))
            db.session.commit()

        except Exception as e:
            print("❌ Error in stream-chat:", e)
            yield f"data: Error: {str(e)}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")

@my_app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

if __name__ == "__main__":
    my_app.run(host="0.0.0.0", port=5000)
