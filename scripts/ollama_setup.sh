#!/bin/bash
# scripts/ollama_setup.sh — Auto-pull models for QTrader
set -e

# Start Ollama in the background
/bin/ollama serve &

# Wait for Ollama to be ready
echo "[OLLAMA] Waiting for server startup (using 'ollama list' check)..."
while ! ollama list > /dev/null 2>&1; do
    sleep 2
done

# Pull models (Idempotent: doesn't re-download if already exists)
echo "[OLLAMA] Pulling Focused Models (Llama 3.2 1B, Qwen 3 Embedding 0.6B, Qwen 3.5 2B)..."
ollama pull llama3.2:1b
ollama pull qwen3-embedding:0.6b
ollama pull qwen3.5:2b
ollama pull gemma4:e2b

echo "[OLLAMA] All models ready!"

# Wait for the background process to stay alive
wait
