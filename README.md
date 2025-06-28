# Flask Ollama Chatbot API

## Overview
This is a Flask-based API with:
- User registration & login (bcrypt)
- Chat endpoint calling Ollama LLM
- SQLite (can switch to Postgres later)
- Flask-Migrate for schema versioning

## How to run

```bash
# Install virtualenv if needed
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up DB
flask --app app/main.py db upgrade

# Start Ollama server
ollama run my-chat

# Run Flask server
python app/main.py

