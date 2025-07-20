# app/pinecone_client.py

from pinecone import Pinecone, ServerlessSpec
import os
from dotenv import load_dotenv

# ✅ Load env vars if you have .env
load_dotenv()

# 👉 Use your real Pinecone API key!
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENV = os.getenv("PINECONE_ENV")

# ✅ Initialize Pinecone client
pc = Pinecone(api_key=PINECONE_API_KEY)

# ✅ Define your index
INDEX_NAME = "tintu-doc-index"
DIMENSION = 768  # <-- match your embedding model dimension!
METRIC = "cosine"

# ✅ Recreate if needed
existing_indexes = pc.list_indexes().names()

if INDEX_NAME in existing_indexes:
    print(f"✅ Index '{INDEX_NAME}' already exists.")
else:
    print(f"⚡ Creating index '{INDEX_NAME}' with dimension {DIMENSION} ...")
    pc.create_index(
        name="tintu-doc-index",
        dimension=768,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1")
    )
    print(f"✅ Index '{INDEX_NAME}' created.")

# ✅ Get index client
index = pc.Index(INDEX_NAME)

def upsert_vectors(vectors, namespace=None):
    """
    vectors = [
      ("id1", [embedding floats], {"metadata": ...}),
      ...
    ]
    """
    print(f"🔄 Upserting {len(vectors)} vectors ...")
    index.upsert(vectors=vectors, namespace=namespace)
    print(f"✅ Upsert done.")

def semantic_search(query_embedding, namespace=None, top_k=5):
    """
    query_embedding: [float, float, ...] (same dimension!)
    """
    return index.query(
        vector=query_embedding,
        top_k=top_k,
        include_metadata=True,
        namespace=namespace
    )
