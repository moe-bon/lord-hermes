use chrono::Utc;
use service_framework_core::pb::service_framework_server::ServiceFrameworkServer;
use service_framework_core::pb::{
    FailClosedPolicy, ServiceDescriptor, ServiceEndpoint, ServicePlane, ServiceState,
};
use service_framework_core::{
    config::Config, db, grpc::ServiceFrameworkGrpc, http, logging, metrics::Metrics,
    validation,
};
use sqlx::postgres::PgPoolOptions;
use std::sync::Arc;
use std::time::Duration;
use tokio::net::TcpListener;

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

    sqlx::migrate!("../../../migrations/postgres/service_framework")
        .run(&pool)
        .await?;

    let self_descriptor = self_descriptor(&config);
    let self_descriptor = validation::normalize_descriptor(self_descriptor)?;

    db::register_service(&pool, &self_descriptor).await?;

    let grpc_service = ServiceFrameworkGrpc::new(pool.clone(), metrics.clone());
    let grpc_addr = config.grpc_addr;

    let grpc_server = tokio::spawn(async move {
        tonic::transport::Server::builder()
            .add_service(ServiceFrameworkServer::new(grpc_service))
            .serve(grpc_addr)
            .await
            .map_err(|err| err.to_string())
    });

    let app_state = Arc::new(http::AppState {
        pool: pool.clone(),
        metrics: metrics.clone(),
    });

    let http_addr = config.http_addr;
    let app = http::router(app_state);

    let http_server = tokio::spawn(async move {
        let listener = TcpListener::bind(http_addr)
            .await
            .map_err(|err| err.to_string())?;

        axum::serve(listener, app)
            .await
            .map_err(|err| err.to_string())
    });

    let heartbeat_pool = pool.clone();
    let heartbeat_service_id = self_descriptor.service_id.clone();
    let heartbeat_interval = Duration::from_secs(config.heartbeat_interval_secs);

    let heartbeat_task = tokio::spawn(async move {
        heartbeat_loop(
            heartbeat_pool,
            heartbeat_service_id,
            heartbeat_interval,
        )
        .await
    });

    tokio::select! {
        _ = tokio::signal::ctrl_c() => {
            tracing::info!("shutdown signal received");
        }
        result = grpc_server => {
            result.map_err(|err| err.to_string())??;
        }
        result = http_server => {
            result.map_err(|err| err.to_string())??;
        }
        result = heartbeat_task => {
            result.map_err(|err| err.to_string())??;
        }
    }

    Ok(())
}

fn self_descriptor(config: &Config) -> ServiceDescriptor {
    ServiceDescriptor {
        service_id: String::new(),
        service_name: config.service_name.clone(),
        version: config.service_version.clone(),
        environment: config.environment.clone(),
        plane: ServicePlane::Control as i32,
        fail_closed_policy: FailClosedPolicy::Shutdown as i32,
        description: "ApexQuant Ultra service framework core".into(),
        capabilities: vec![
            "SERVICE_REGISTRY".into(),
            "SERVICE_HEARTBEAT".into(),
            "SERVICE_METADATA".into(),
        ],
        permissions: vec!["SERVICE_REGISTRY_WRITE".into()],
        endpoints: vec![
            ServiceEndpoint {
                name: "http".into(),
                protocol: "http".into(),
                uri: format!("http://{}", config.http_addr),
                port: config.http_addr.port() as i32,
            },
            ServiceEndpoint {
                name: "grpc".into(),
                protocol: "grpc".into(),
                uri: format!("grpc://{}", config.grpc_addr),
                port: config.grpc_addr.port() as i32,
            },
        ],
        dependencies: vec!["postgres".into()],
    }
}

async fn heartbeat_loop(
    pool: sqlx::PgPool,
    service_id: String,
    interval: Duration,
) -> Result<(), String> {
    let mut ticker = tokio::time::interval(interval);
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);

    loop {
        ticker.tick().await;

        let result = db::record_heartbeat(
            &pool,
            &service_id,
            ServiceState::Ready as i32,
            "service-framework-core heartbeat",
            Utc::now(),
        )
        .await;

        if let Err(err) = result {
            tracing::error!(error = %err, "heartbeat failed");
        }
    }
}