mod models;
mod repository;
mod routes;

use axum::{routing::{get, post}, Router};
use repository::SourceRepository;
use sqlx::postgres::PgPoolOptions;
use std::sync::Arc;
use tower_http::trace::TraceLayer;
use tracing::info;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_| "apex_md_registry=info,tower_http=info".into()))
        .with(tracing_subscriber::fmt::layer().json())
        .init();

    info!("ApexQuant Market Data Registry Starting...");
    let database_url = std::env::var("DATABASE_URL").unwrap_or_else(|_| "postgres://apex:apexquantpostgres123@postgres:5432/apexquant".to_string());
    let pool = PgPoolOptions::new().max_connections(50).connect(&database_url).await?;

    sqlx::migrate!("../migrations/postgres").run(&pool).await?;
    info!("Database migrations applied successfully.");

    let repo = Arc::new(SourceRepository::new(pool));
    let app = Router::new()
        .route("/healthz", get(routes::healthz))
        .route("/v1/sources", post(routes::create_source))
        .route("/v1/assignments", post(routes::assign_role))
        .layer(TraceLayer::new_for_http())
        .with_state(repo);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8095").await?;
    info!("Listening on 0.0.0.0:8095");
    axum::serve(listener, app).await?;
    Ok(())
}
