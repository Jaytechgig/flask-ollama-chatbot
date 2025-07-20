from flask import Blueprint, request, jsonify
import fitz  # PyMuPDF
import os
import logging
from app.pinecone_client import upsert_vectors
from app.embedding_helper import embed_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

pdf_bp = Blueprint('pdf_bp', __name__)

@pdf_bp.route("/upload-pdf", methods=["POST"])
def extractPDFText():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No file part"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"success": False, "message": "No selected file"}), 400

    if not file.filename.lower().endswith('.pdf'):
        return jsonify({"success": False, "message": "Only PDF files are allowed"}), 400

    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    MAX_SIZE = 5 * 1024 * 1024  # 5 MB
    logger.info(f"Received file: {file.filename}, Size: {file_size} bytes")

    if file_size > MAX_SIZE:
        return jsonify({"success": False, "message": f"File too large. Max {MAX_SIZE // 1024} KB allowed."}), 400

    try:
        pdf_bytes = file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        logger.error(f"Failed to open PDF: {e}")
        return jsonify({"success": False, "message": "Invalid or corrupt PDF file"}), 400

    pages = []
    vectors = []

    for i, page in enumerate(doc, start=1):
        page_text = page.get_text().strip()
        if not page_text:
            continue

        # 📌 Add to local response
        pages.append({
            "page": i,
            "content": page_text,
            "preview": page_text[:100]
        })

        # 📌 Embed and prepare for Pinecone
        embedding = embed_text(page_text)
        vector_id = f"{file.filename}-page-{i}"
        metadata = {
            "page": i,
            "filename": file.filename,
            "content": page_text   # Optional preview for retrieval
        }
        vectors.append((vector_id, embedding, metadata))

    doc.close()

    logger.info(f"Extracted {len(pages)} pages, indexing {len(vectors)} vectors to Pinecone")
    if vectors:
        upsert_vectors(vectors)

    total_chars = sum(len(p['content']) for p in pages)
    logger.info(f"Total {total_chars} characters extracted")

    if total_chars == 0:
        return jsonify({"success": False, "message": "No extractable text found"}), 400

    return jsonify({
        "success": True,
        "filename": file.filename,
        "page_count": len(pages),
        "pages": pages
    })
