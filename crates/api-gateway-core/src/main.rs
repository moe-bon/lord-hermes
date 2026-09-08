use api_gateway_core::{
    config::Config, http, logging, metrics::Metrics, persistence, registry::RouteRegistry,
};
use sqlx::postgres::PgPoolOptions;
use std::sync::Arc;
use std::time::Duration;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    logging::init();

    let config = Config::from_env()?;
    let metrics = Arc::new(Metrics::new());
    let registry = RouteRegistry::new(config.upstreams.clone());

    let pool = if let Some(database_url) = &config.database_url {
        let pool = PgPoolOptions::new()
            .max_connections(5)
            .acquire_timeout(Duration::from_secs(5))
            .connect(database_url)
            .await?;

        persistence::migrate(&pool).await?;
        persistence::persist_registry(&pool, &config.environment, &registry).await?;

        Some(pool)
    } else {
        None
    };

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(config.request_timeout_secs))
        .no_proxy()
        .build()?;

    let app_state = Arc::new(http::AppState {
        config: config.clone(),
        registry,
        metrics,
        client,
        pool,
    });

    let app = http::router(app_state);
    let listener = tokio::net::TcpListener::bind(config.http_addr).await?;

    tracing::info!(
        environment = %config.environment,
        addr = %config.http_addr,
        "API gateway starting"
    );

    axum::serve(listener, app).await?;

    Ok(())
}