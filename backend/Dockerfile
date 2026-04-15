ARG PYTHON_BASE_IMAGE=python:3.11-slim

FROM ${PYTHON_BASE_IMAGE} AS whisper_cpp_builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git cmake build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
        git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git /tmp/whisper.cpp; \
        cmake -S /tmp/whisper.cpp -B /tmp/whisper.cpp/build -DCMAKE_BUILD_TYPE=Release; \
        cmake --build /tmp/whisper.cpp/build --config Release -j"$(nproc)"; \
        if [ -f /tmp/whisper.cpp/build/bin/whisper-cli ]; then \
            cp /tmp/whisper.cpp/build/bin/whisper-cli /tmp/whisper-cli; \
        elif [ -f /tmp/whisper.cpp/build/bin/main ]; then \
            cp /tmp/whisper.cpp/build/bin/main /tmp/whisper-cli; \
        else \
            echo "whisper.cpp CLI binary not found"; \
            exit 1; \
        fi; \
        chmod +x /tmp/whisper-cli

FROM ${PYTHON_BASE_IMAGE}

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
    && apt-get install -y --no-install-recommends curl ffmpeg espeak-ng ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=whisper_cpp_builder /tmp/whisper-cli /app/whisper.cpp/whisper-cli

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
