from __future__ import annotations

import os
from functools import lru_cache

from contract import cosine_similarity, validate_text, validate_texts
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

MODEL_NAME = os.environ.get(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)

app = FastAPI(title="wiki-polis embedding sidecar", version="1.0.0")


class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=32)
    normalize: bool = True


class EmbedResponse(BaseModel):
    model: str
    dimension: int
    embeddings: list[list[float]]


class SimilarityRequest(BaseModel):
    left: str
    right: str


class SimilarityResponse(BaseModel):
    model: str
    similarity: float


@lru_cache(maxsize=1)
def _model():
    return SentenceTransformer(MODEL_NAME)


def _encode(texts: list[str], *, normalize: bool = True) -> list[list[float]]:
    vectors = _model().encode(texts, normalize_embeddings=normalize)
    return [[float(value) for value in row] for row in vectors]


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME}


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest):
    try:
        texts = validate_texts(req.texts)
        embeddings = _encode(texts, normalize=req.normalize)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    dimension = len(embeddings[0]) if embeddings else 0
    return {"model": MODEL_NAME, "dimension": dimension, "embeddings": embeddings}


@app.post("/similarity", response_model=SimilarityResponse)
def similarity(req: SimilarityRequest):
    try:
        texts = [validate_text(req.left), validate_text(req.right)]
        left, right = _encode(texts, normalize=True)
        score = cosine_similarity(left, right)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"model": MODEL_NAME, "similarity": score}
