#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

MODE="${1:-generate}"
PROTO_SRC_DIR="$ROOT_DIR/services/nestjs/proto/v1"
NESTJS_PROTO_MIRROR_DIR="$ROOT_DIR/services/nestjs/dist-proto/v1"
PYTHON_GEN_DIR="$ROOT_DIR/services/python/common/generated"

mkdir -p "$NESTJS_PROTO_MIRROR_DIR" "$PYTHON_GEN_DIR"

if [[ "$MODE" != "generate" && "$MODE" != "check" ]]; then
  echo "Usage: $0 [generate|check]" >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

if [[ "$MODE" == "generate" ]]; then
  echo "[PROTO] Generating python bindings from $PROTO_SRC_DIR"
  python3 -m grpc_tools.protoc \
    -I="$PROTO_SRC_DIR" \
    --python_out="$PYTHON_GEN_DIR" \
    --grpc_python_out="$PYTHON_GEN_DIR" \
    "$PROTO_SRC_DIR"/*.proto

  echo "[PROTO] Mirroring .proto files for runtime loaders"
  cp "$PROTO_SRC_DIR"/*.proto "$NESTJS_PROTO_MIRROR_DIR"/
  echo "[PROTO] Done"
  exit 0
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

python3 -m grpc_tools.protoc \
  -I="$PROTO_SRC_DIR" \
  --python_out="$TMP_DIR" \
  --grpc_python_out="$TMP_DIR" \
  "$PROTO_SRC_DIR"/*.proto

if ! diff -qr "$TMP_DIR" "$PYTHON_GEN_DIR" >/dev/null 2>&1; then
  echo "[PROTO] Drift detected in generated python bindings. Run generate_protos.sh generate" >&2
  exit 1
fi

echo "[PROTO] No drift detected"
