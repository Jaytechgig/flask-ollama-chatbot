from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
from ariadne import graphql_sync
from app.constants import PLAYGROUND_HTML
from app.models import db, User, ChatHistory
from app.schema import schema
from app.pdf_upload import pdf_bp
from ariadne.file_uploads import combine_multipart_data
import json
import ollama
import os

MODEL_NAME = "my-chat"

UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

my_app = Flask(__name__)
CORS(my_app)  # ✅ Allow React frontend to call APIs

my_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
db.init_app(my_app)
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
            stream = ollama.chat(
                model=MODEL_NAME,
                messages=messages,
                stream=True,
                options={
                    "num_predict": 200,
                    "temperature": 0.7
                }
            )

            full_reply = ""
            for chunk in stream:
                token = chunk['message']['content']
                full_reply += token
                # Stream each chunk in SSE format
                yield f"data: {json.dumps({'token': token})}\n\n"

            # Save both after the full stream is done
            db.session.add(ChatHistory(user_id=user.id, role="user", content=user_input))
            db.session.add(ChatHistory(user_id=user.id, role="assistant", content=full_reply))
            db.session.commit()

        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")

# ✅ NEW: Serve stylized images from /uploads/
@my_app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

if __name__ == "__main__":
    my_app.run(debug=True)
