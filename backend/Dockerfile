FROM python:3.11-slim

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_FALLBACK_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=240 \
    PIP_PROGRESS_BAR=off \
    PIP_INDEX_URL=${PIP_INDEX_URL}

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg espeak-ng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN set -eux; \
        pip_install_with_index() { \
            index_url="$1"; \
            package_args="$2"; \
            PIP_INDEX_URL="$index_url" pip install --no-cache-dir --prefer-binary --retries 12 --timeout 240 ${package_args}; \
        }; \
        install_with_retry() { \
            package_args="$1"; \
            for index_url in "${PIP_INDEX_URL}" "${PIP_FALLBACK_INDEX_URL}"; do \
                [ -n "${index_url}" ] || continue; \
                success=0; \
                for attempt in 1 2 3 4 5; do \
                    if pip_install_with_index "${index_url}" "${package_args}"; then \
                        success=1; \
                        break; \
                    fi; \
                    echo "pip install failed (attempt ${attempt}/5) index=${index_url}: ${package_args}"; \
                    sleep 5; \
                done; \
                if [ "$success" -eq 1 ]; then \
                    return 0; \
                fi; \
            done; \
            echo "pip install failed after retries: ${package_args}"; \
            exit 1; \
        }; \
        install_with_retry "-r /app/requirements.txt"; \
        install_with_retry "piper-tts"

COPY app /app/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
