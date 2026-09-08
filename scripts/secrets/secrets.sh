name: Secrets

on:
  push:
    branches:
      - main
  pull_request:
    branches:
      - main

jobs:
  python-secrets-tests:
    name: Python Secrets Tests
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Run secrets package tests
        run: |
          cd python/apexquant-secrets
          uv sync --all-extras
          uv run pytest

  rust-secrets-tests:
    name: Rust Secrets Tests
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Install Rust toolchain
        uses: dtolnay/rust-toolchain@1.81.0

      - name: Run apex-secrets tests
        run: cargo test --package apex-secrets

  secret-scan:
    name: Secret Reference Scan
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Scan environment template
        run: ./scripts/secrets/scan-env-example.sh