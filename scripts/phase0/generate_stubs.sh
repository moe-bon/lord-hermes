#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "🛠️  Generating Phase 0 Microservice Stubs..."
mkdir -p infra/docker/dockerfiles

# Helper for Python FastAPI stubs
create_python_stub() {
  local name=$1
  local port=$2
  local dockerfile_name=$3
  local dir="python/apexquant-$name"
  local pkg="apexquant_$(echo $name | tr '-' '_')"
  
  mkdir -p "$dir/src/$pkg"
  
  cat > "$dir/pyproject.toml" << PYEOF
[project]
name = "apexquant-$name"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["fastapi>=0.115", "uvicorn>=0.30"]
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
[tool.hatch.build.targets.wheel]
packages = ["src/$pkg"]
PYEOF

  cat > "$dir/src/$pkg/app.py" << APPEOF
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
app = FastAPI(title="apexquant-$name")
@app.get("/healthz")
def healthz(): return {"status": "ok"}
@app.get("/readyz")
def readyz(): return {"ready": True}
@app.get("/metrics")
def metrics(): return PlainTextResponse("# metrics stub\n")
APPEOF

  touch "$dir/src/$pkg/__init__.py"

  cat > "infra/docker/dockerfiles/$dockerfile_name" << DKEOF
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY $dir ./$dir
RUN pip install --no-cache-dir ./$dir
EXPOSE $port
CMD ["uvicorn", "$pkg.app:app", "--host", "0.0.0.0", "--port", "$port"]
DKEOF
  echo "  ✅ Created stub for $name (Port $port)"
}

# Generate Python Stubs (Matching exact Dockerfile names from your build logs)
create_python_stub "database-infrastructure-core" "8081" "Dockerfile.database-infrastructure"
create_python_stub "api-gateway" "8085" "Dockerfile.api-gateway"
create_python_stub "auth-core" "8086" "Dockerfile.auth-core"
create_python_stub "audit-core" "8087" "Dockerfile.audit-core"
create_python_stub "logging-core" "8088" "Dockerfile.logging-core"
create_python_stub "tracing-core" "8089" "Dockerfile.tracing-core"
create_python_stub "feature-flags-core" "8091" "Dockerfile.feature-flags-core"
create_python_stub "config-validation-core" "8092" "Dockerfile.config-validation-core"
create_python_stub "backup-recovery-core" "8093" "Dockerfile.backup-recovery-core"
create_python_stub "disaster-recovery-core" "8094" "Dockerfile.disaster-recovery-core"

# Storage Bootstrap (Just a simple script that exits)
cat > infra/docker/dockerfiles/Dockerfile.python-service << 'DKEOF'
FROM python:3.13-slim
CMD ["echo", "Storage bootstrap complete"]
DKEOF
echo "  ✅ Created stub for storage-bootstrap"

# Generate Rust Stub for Service Framework
mkdir -p crates/common/apex-service-framework/src
cat > crates/common/apex-service-framework/Cargo.toml << 'RSEOF'
[package]
name = "apex-service-framework"
version = "0.1.0"
edition = "2021"
[dependencies]
actix-web = "4"
serde_json = "1"
RSEOF

cat > crates/common/apex-service-framework/src/main.rs << 'RSEOF'
use actix_web::{get, App, HttpServer, HttpResponse};
#[get("/healthz")]
async fn healthz() -> HttpResponse { HttpResponse::Ok().json(serde_json::json!({"status": "ok"})) }
#[get("/metrics")]
async fn metrics() -> HttpResponse { HttpResponse::Ok().body("# metrics\n") }
#[actix_web::main]
async fn main() -> std::io::Result<()> {
    HttpServer::new(|| App::new().service(healthz).service(metrics))
        .bind("0.0.0.0:8080")?.run().await
}
RSEOF

cat > infra/docker/dockerfiles/Dockerfile.service-framework << 'DKEOF'
FROM rust:1.81-bookworm AS builder
WORKDIR /workspace
COPY crates/common/apex-service-framework ./apex-service-framework
WORKDIR /workspace/apex-service-framework
RUN cargo build --release

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder /workspace/apex-service-framework/target/release/apex-service-framework /usr/local/bin/
EXPOSE 8080
CMD ["/usr/local/bin/apex-service-framework"]
DKEOF
echo "  ✅ Created stub for service-framework-core (Port 8080)"

echo ""
echo "🎉 All Phase 0 stubs generated successfully!"
