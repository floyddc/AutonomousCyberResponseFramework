#!/bin/bash

set -e

echo "================================"
echo "Run Qwen3 4B..."
echo "================================"

ollama run qwen3:4b "hello"

echo ""
echo "Warm-up completed."

echo "================================"
echo "Run Qwen3-8B..."
echo "================================"

ollama run qwen3:8b "hello"

echo ""
echo "Warm-up completed."

echo "================================"
echo "Done."
echo "================================"