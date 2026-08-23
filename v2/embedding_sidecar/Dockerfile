FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/models/sentence-transformers

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# The sidecar does not use a GPU. Installing torch from its dedicated CPU
# index avoids pulling several gigabytes of CUDA libraries from the default
# Linux wheel before sentence-transformers resolves the rest of the stack.
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        "$(grep '^torch==' requirements.txt)" \
    && pip install --no-cache-dir -r requirements.txt

COPY app.py contract.py ./

EXPOSE 8015
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8015"]
