# Embedding sidecar (#208)

Small FastAPI service for semantic similarity and embeddings. It is intended to run on
the existing VPS next to Particiapi/Polis, not on Toolforge.

Default model:
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

Runtime notes:

- CPU only is fine for submission-time similarity checks.
- First request downloads/loads the model and is slow; keep the container warm.
- Model cache lives in the `embedding-models` Docker volume.
- Bind to loopback or an internal network only; Flask should call it over internal HTTP.

## Run on the VPS

```bash
cd ~/wiki-polis/v2/embedding_sidecar
docker-compose -f docker-compose.embedding.yaml up -d --build
curl -fsS http://127.0.0.1:8015/health
```

## HTTP contract

### `GET /health`

Response:

```json
{"status": "ok", "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"}
```

### `POST /similarity`

Request:

```json
{"left": "Parent statement text", "right": "Derived statement text"}
```

Response:

```json
{
  "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
  "similarity": 0.8731
}
```

`similarity` is cosine similarity in the range `-1.0` to `1.0`; with normalized sentence
embeddings, practical values are usually `0.0` to `1.0`.

### `POST /embed`

Request:

```json
{"texts": ["first statement", "second statement"], "normalize": true}
```

Response:

```json
{
  "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
  "dimension": 384,
  "embeddings": [[0.0123, -0.0456], [0.0789, 0.0101]]
}
```

The example vectors are truncated for readability; real responses include all
dimensions. Limits: max 32 texts per request, max 2000 characters per text.
