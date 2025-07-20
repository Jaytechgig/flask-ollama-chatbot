# app/embedding_helper.py

from sentence_transformers import SentenceTransformer

# Load a local embedding model — you can pick any you like!
# 'all-MiniLM-L6-v2' is fast, small, and dimension 384.
# For larger, more accurate vectors, use 'all-mpnet-base-v2' (dimension 768).
model = SentenceTransformer('all-mpnet-base-v2')

def embed_text(text):
    """
    Return a list of floats (the embedding).
    """
    embedding = model.encode(text).tolist()
    return embedding
