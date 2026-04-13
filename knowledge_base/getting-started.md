# Local Voice RAG Assistant

This file is a starter knowledge document.

- System mode: full duplex voice over WebSocket
- STT: Faster-Whisper with VAD
- Retrieval: LanceDB (fallback: file retrieval)
- LLM: Ollama streaming generation
- TTS: Piper raw PCM streaming

You can add more markdown files to this folder, then run:

python -m app.knowledge_sync

inside the backend container to refresh vectors.
