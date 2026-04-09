#!/bin/bash

# Hybrid Platform Protocol Generator
# Compiles .proto files into TypeScript (for Control Plane) and Python (for Compute Plane)

set -e

PROTO_DIR="../../proto"
NESTJS_OUT_DIR="../../services/nestjs/src/generated"
PYTHON_OUT_DIR="../../services/python/common/generated"

# Ensure directories exist
mkdir -p "$NESTJS_OUT_DIR"
mkdir -p "$PYTHON_OUT_DIR"

echo "[PROTO] Generating Python bindings..."
python3 -m grpc_tools.protoc \
    -I="$PROTO_DIR" \
    --python_out="$PYTHON_OUT_DIR" \
    --grpc_python_out="$PYTHON_OUT_DIR" \
    "$PROTO_DIR"/*.proto

echo "[PROTO] Generating TypeScript bindings (for NestJS proto-loader)..."
# NestJS usually uses proto-loader at runtime, but we can generate types for dev experience
# For this template, we ensure the .proto files are accessible to the nestjs services
cp "$PROTO_DIR"/*.proto "$NESTJS_OUT_DIR"/

echo "[PROTO] Generation complete."
