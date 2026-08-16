#!/bin/bash
# Verify local Ollama server status and model availability.

echo "🔍 Checking local Ollama installation..."

# Check if ollama is available on command line
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama is not installed or not in PATH."
    echo "👉 Install it from: https://ollama.com/download"
    exit 1
fi

# Check if Ollama service is responsive
echo "🌐 Checking connection to http://localhost:11434..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:11434/api/tags)

if [ "$HTTP_STATUS" -ne 200 ]; then
    echo "❌ Ollama server is not running."
    echo "👉 Start Ollama app or run: ollama serve"
    exit 1
fi

echo "✅ Ollama is running and responding."

# Check if gemma:e2b-it or gemma4:e2b is installed
echo "📦 Checking available models..."
MODELS=$(curl -s http://localhost:11434/api/tags)

if echo "$MODELS" | grep -q "gemma:e2b-it"; then
    echo "✅ Found local model: gemma:e2b-it"
elif echo "$MODELS" | grep -q "gemma4:e2b"; then
    echo "✅ Found local model: gemma4:e2b"
else
    echo "⚠️ Local worker model not found."
    echo "👉 Run: ollama pull gemma:e2b-it"
    exit 1
fi

echo "🎉 Ollama local worker is fully ready!"
exit 0
