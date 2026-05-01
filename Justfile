#!/usr/bin/env just --justfile

SEPARATOR := `printf '%0.s-' {1..60}`
PROTO_PATH := "protos/vendor"
PYTHON_OUT_PATH := "src/ctrader_api_client/_internal/proto"

default: help

# Print this help message
help:
    just --list

# Spin up documentation server using MkDocs
documentation:
    uv run mkdocs serve

# Run all CI steps: linting, formatting, type checking
ci directory='':
    @just lint {{directory}}
    @just fmt {{directory}}
    @just type-check {{directory}}
    @just test {{directory}}

# Lint the codebase using ruff, optionally specifying a directory to lint.
lint directory='':
    uv run ruff check --fix {{directory}}

# Format the codebase using ruff, optionally specifying a directory to format.
fmt directory='':
    uv run ruff format {{directory}}

# Run type checking using ty, optionally specifying a directory to check.
type-check directory='':
    uv run zuban check {{directory}}

# Run tests using pytest, optionally specifying a directory to test.
test directory='':
    uv run pytest {{directory}}

# Update .proto files to a specific version. Defaults to 'main' if no version is provided.
update-proto version='':
    ./protos/update.sh {{version}}

# Generate Python code from .proto files. This should be run after updating the .proto files.
@compile-proto:
     echo {{SEPARATOR}}
     echo "Compiling .proto files from {{PROTO_PATH}}/ to Python code under {{PYTHON_OUT_PATH}}/"
     uv run protoc -I={{PROTO_PATH}} \
            --python_betterproto_out={{PYTHON_OUT_PATH}} \
            {{PROTO_PATH}}/*.proto
     echo {{SEPARATOR}}
     echo "Fixing cross-module imports..."
     uv run python scripts/fix_proto_imports.py
     echo "Formatting generated code with ruff..."
     @uv run ruff check {{PYTHON_OUT_PATH}} --fix
     @uv run ruff format {{PYTHON_OUT_PATH}}
