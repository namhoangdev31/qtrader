#!/bin/bash
# scripts/ollama_setup.sh — Auto-pull models for QTrader
set -e

# Start Ollama in the background
/bin/ollama serve &

# Wait for Ollama to be ready
echo "[OLLAMA] Waiting for server startup..."
while ! curl -s http://localhost:11434/api/tags > /dev/null; do
    sleep 2
done

# Pull models (Idempotent: doesn't re-download if already exists)
echo "[OLLAMA] Pulling models (phi3:mini, qwen2:1.5b)..."
ollama pull phi3:mini
ollama pull qwen2:1.5b

echo "[OLLAMA] All models ready!"

# Wait for the background process to stay alive
wait
