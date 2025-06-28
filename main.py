from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from models import db, User, ChatHistory
import bcrypt
import ollama

my_app = Flask(__name__)
my_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db.init_app(my_app)

migrate = Migrate(my_app, db)

MODEL_NAME = "my-chat"

with my_app.app_context():
    db.create_all()


# ========= ROUTES ==========
@my_app.route("/")
def home():
    return """
    <h2>✅ Flask Ollama Chatbot is Running!</h2>
    <p>Available endpoints:</p>
    <ul>
      <li><strong>POST</strong> /register — register a new user</li>
      <li><strong>POST</strong> /login — log in an existing user</li>
      <li><strong>POST</strong> /chat — send a message to the chatbot</li>
    </ul>
    <p>Access me on this device: <code>http://127.0.0.1:5000/</code></p>
    <p>Or on your LAN: <code>http://192.168.31.226:5000/</code></p>
    """


@my_app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data["username"]
    password = data["password"]

    if User.query.filter_by(username=username).first():
        return jsonify({"success": False, "message": "Username already exists"}), 409

    pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    new_user = User(username=username, password_hash=pw_hash.decode('utf-8'))
    db.session.add(new_user)
    db.session.commit()

    return jsonify({"success": True, "message": "User registered!"})

@my_app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data["username"]
    password = data["password"]

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    if bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
        return jsonify({"success": True, "message": "Login successful!"})
    else:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

@my_app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    username = data["username"]
    user_input = data["message"]

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"success": False, "message": "Invalid user"}), 401

    # Load last 5 messages for context
    history = ChatHistory.query.filter_by(user_id=user.id).order_by(ChatHistory.id.desc()).limit(5).all()
    messages = [{"role": "system", "content": "You are Tintu 🧸, a helpful bot."}]
    for h in reversed(history):
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": user_input})

    # Call Ollama
    response = ollama.chat(model=MODEL_NAME, messages=messages)
    bot_reply = response["message"]["content"]

    # Save both to DB
    db.session.add(ChatHistory(user_id=user.id, role="user", content=user_input))
    db.session.add(ChatHistory(user_id=user.id, role="assistant", content=bot_reply))
    db.session.commit()

    return jsonify({"reply": bot_reply})

if __name__ == "__main__":
    my_app.run(host="0.0.0.0", port=5000, debug=True)