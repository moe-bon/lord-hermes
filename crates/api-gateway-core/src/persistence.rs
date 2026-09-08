use crate::errors::GatewayError;
use crate::registry::RouteRegistry;
use serde_json::Value;
use sqlx::PgPool;

pub async fn migrate(pool: &PgPool) -> Result<(), GatewayError> {
    sqlx::migrate!("../../../migrations/postgres/api_gateway")
        .run(pool)
        .await?;

    Ok(())
}

pub async fn persist_registry(
    pool: &PgPool,
    environment: &str,
    registry: &RouteRegistry,
) -> Result<(), GatewayError> {
    let mut tx = pool.begin().await?;

    for upstream in registry.services() {
        sqlx::query(
            r#"
            INSERT INTO api_gateway.services (
                service_name,
                plane,
                base_url,
                environment
            )
            VALUES (
                $1,
                $2,
                $3,
                $4
            )
            ON CONFLICT (service_name) DO UPDATE SET
                plane = EXCLUDED.plane,
                base_url = EXCLUDED.base_url,
                environment = EXCLUDED.environment,
                active = TRUE,
                updated_at = now()
            "#,
        )
        .bind(&upstream.service_name)
        .bind(&upstream.plane)
        .bind(upstream.base_url.as_str())
        .bind(environment)
        .execute(&mut *tx)
        .await?;

        let path_prefix = format!("/api/{}", upstream.service_name);

        sqlx::query(
            r#"
            INSERT INTO api_gateway.routes (
                service_name,
                method,
                path_prefix,
                api_version,
                auth_required,
                description
            )
            VALUES (
                $1,
                'ANY',
                $2,
                'v1',
                FALSE,
                'Gateway route prefix'
            )
            ON CONFLICT (service_name, method, path_prefix, api_version) DO UPDATE SET
                auth_required = FALSE,
                description = EXCLUDED.description,
                updated_at = now()
            "#,
        )
        .bind(&upstream.service_name)
        .bind(&path_prefix)
        .execute(&mut *tx)
        .await?;
    }

    tx.commit().await?;

    Ok(())
}

pub async fn persist_verification(
    pool: &PgPool,
    environment: &str,
    ok: bool,
    report: Value,
) -> Result<(), GatewayError> {
    sqlx::query(
        r#"
        INSERT INTO api_gateway.verification_runs (
            environment,
            generated_at,
            ok,
            report
        )
        VALUES (
            $1,
            now(),
            $2,
            $3
        )
        "#,
    )
    .bind(environment)
    .bind(ok)
    .bind(report)
    .execute(pool)
    .await?;

    Ok(())
}