FROM python:3.11-slim

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL}

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg espeak-ng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN set -eux; \
        install_with_retry() { \
            package_args="$1"; \
            success=0; \
            for attempt in 1 2 3 4 5; do \
                if pip install --no-cache-dir --retries 10 --timeout 120 ${package_args}; then \
                    success=1; \
                    break; \
                fi; \
                echo "pip install failed (attempt ${attempt}/5): ${package_args}"; \
                sleep 5; \
            done; \
            if [ "$success" -ne 1 ]; then \
                echo "pip install failed after retries: ${package_args}"; \
                exit 1; \
            fi; \
        }; \
        install_with_retry "-r /app/requirements.txt"; \
        install_with_retry "piper-tts"

COPY app /app/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
