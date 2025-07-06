from flask import Flask, request, jsonify
from flask_cors import CORS
from ariadne import graphql_sync
from app.constants import PLAYGROUND_HTML
from app.models import db
from app.schema import schema
from app.pdf_upload import pdf_bp
from ariadne.file_uploads import combine_multipart_data

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
        import json
        operations = json.loads(request.form.get("operations"))
        file_map = json.loads(request.form.get("map"))
        files = dict(request.files)
        data = combine_multipart_data(operations, file_map, files)
    else:
        data = request.get_json()

    success, result = graphql_sync(schema, data, context_value=request, debug=True)
    status_code = 200 if success else 400
    return jsonify(result), status_code



if __name__ == "__main__":
    my_app.run(debug=True)
