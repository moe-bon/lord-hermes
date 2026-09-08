use database_infrastructure_core::{
    config::Config, db, http, logging, metrics::Metrics,
};
use sqlx::postgres::PgPoolOptions;
use std::sync::Arc;
use std::time::Duration;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    logging::init();

    let config = Config::from_env()?;
    let metrics = Arc::new(Metrics::new());

    let pool = PgPoolOptions::new()
        .max_connections(config.max_db_connections)
        .acquire_timeout(Duration::from_secs(5))
        .connect(&config.database_url)
        .await?;

    sqlx::migrate!("../../../migrations/postgres/database_infrastructure")
        .run(&pool)
        .await?;

    if std::env::args().any(|arg| arg == "--check") {
        let report =
            db::run_checks(&pool, &config.environment, &config.instance_name).await?;

        let run_id = db::persist_report(&pool, &report).await?;

        println!("{}", serde_json::to_string_pretty(&report)?);
        println!("verification_run_id={run_id}");

        if report.ok {
            std::process::exit(0);
        } else {
            std::process::exit(1);
        }
    }

    let app_state = Arc::new(http::AppState {
        pool,
        metrics,
        config: config.clone(),
    });

    let app = http::router(app_state);
    let listener = tokio::net::TcpListener::bind(config.http_addr).await?;

    tracing::info!(
        service = %config.service_name,
        version = %config.service_version,
        environment = %config.environment,
        addr = %config.http_addr,
        "database infrastructure service starting"
    );

    axum::serve(listener, app).await?;

    Ok(())
}