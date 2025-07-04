# app.py

from flask import Flask, request, jsonify
from ariadne import graphql_sync
from app.constants import PLAYGROUND_HTML
from flask_sqlalchemy import SQLAlchemy
from app.models import db
from app.schema import schema

my_app = Flask(__name__)
my_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
db.init_app(my_app)

with my_app.app_context():
    db.create_all()

@my_app.route("/graphql", methods=["GET"])
def graphql_playground():
    return PLAYGROUND_HTML, 200

@my_app.route("/graphql", methods=["POST"])
def graphql_server():
    data = request.get_json()
    success, result = graphql_sync(schema, data, context_value=request, debug=True)
    status_code = 200 if success else 400
    return jsonify(result), status_code

if __name__ == "__main__":
    my_app.run(debug=True)
