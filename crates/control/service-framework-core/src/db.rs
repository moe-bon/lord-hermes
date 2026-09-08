use crate::errors::Error;
use crate::pb::{ServiceDescriptor, ServiceEndpoint};
use crate::validation;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value as JsonValue};
use sqlx::{PgPool, QueryBuilder};

#[derive(Debug, sqlx::FromRow, Serialize)]
pub struct ServiceRecord {
    pub service_id: String,
    pub service_name: String,
    pub version: String,
    pub environment: String,
    pub plane: String,
    pub fail_closed_policy: String,
    pub description: String,
    pub capabilities: JsonValue,
    pub permissions: JsonValue,
    pub endpoints: JsonValue,
    pub dependencies: JsonValue,
    pub state: String,
    pub last_heartbeat_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Serialize, Deserialize)]
struct EndpointJson {
    name: String,
    protocol: String,
    uri: String,
    port: i32,
}

const SELECT_COLUMNS: &str = r#"
    service_id,
    service_name,
    version,
    environment,
    plane::text AS plane,
    fail_closed_policy::text AS fail_closed_policy,
    description,
    capabilities,
    permissions,
    endpoints,
    dependencies,
    state::text AS state,
    last_heartbeat_at,
    created_at,
    updated_at
"#;

pub async fn register_service(
    pool: &PgPool,
    descriptor: &ServiceDescriptor,
) -> Result<ServiceRecord, Error> {
    let plane = validation::plane_to_db(descriptor.plane)?;
    let fail_closed_policy = validation::policy_to_db(descriptor.fail_closed_policy)?;

    let capabilities = serde_json::to_value(&descriptor.capabilities)?;
    let permissions = serde_json::to_value(&descriptor.permissions)?;
    let dependencies = serde_json::to_value(&descriptor.dependencies)?;

    let endpoint_jsons: Vec<EndpointJson> = descriptor
        .endpoints
        .iter()
        .map(|endpoint| EndpointJson {
            name: endpoint.name.clone(),
            protocol: endpoint.protocol.clone(),
            uri: endpoint.uri.clone(),
            port: endpoint.port,
        })
        .collect();

    let endpoints = serde_json::to_value(&endpoint_jsons)?;

    let sql = format!(
        r#"
        INSERT INTO service_framework.service_registry (
            service_id,
            service_name,
            version,
            environment,
            plane,
            fail_closed_policy,
            description,
            capabilities,
            permissions,
            endpoints,
            dependencies,
            state,
            last_heartbeat_at
        )
        VALUES (
            $1,
            $2,
            $3,
            $4,
            $5::service_framework.service_plane,
            $6::service_framework.fail_closed_policy,
            $7,
            $8,
            $9,
            $10,
            $11,
            'STARTING'::service_framework.service_state,
            now()
        )
        ON CONFLICT (service_id) DO UPDATE SET
            service_name = EXCLUDED.service_name,
            version = EXCLUDED.version,
            environment = EXCLUDED.environment,
            plane = EXCLUDED.plane,
            fail_closed_policy = EXCLUDED.fail_closed_policy,
            description = EXCLUDED.description,
            capabilities = EXCLUDED.capabilities,
            permissions = EXCLUDED.permissions,
            endpoints = EXCLUDED.endpoints,
            dependencies = EXCLUDED.dependencies,
            state = 'STARTING'::service_framework.service_state,
            last_heartbeat_at = now()
        RETURNING {SELECT_COLUMNS}
        "#
    );

    let record = sqlx::query_as::<_, ServiceRecord>(&sql)
        .bind(&descriptor.service_id)
        .bind(&descriptor.service_name)
        .bind(&descriptor.version)
        .bind(&descriptor.environment)
        .bind(plane)
        .bind(fail_closed_policy)
        .bind(&descriptor.description)
        .bind(&capabilities)
        .bind(&permissions)
        .bind(&endpoints)
        .bind(&dependencies)
        .fetch_one(pool)
        .await?;

    Ok(record)
}

pub async fn record_heartbeat(
    pool: &PgPool,
    service_id: &str,
    state: i32,
    detail: &str,
    observed_at: DateTime<Utc>,
) -> Result<ServiceRecord, Error> {
    let state_db = validation::state_to_db(state)?;
    let payload = json!({ "detail": detail });

    let mut tx = pool.begin().await?;

    let update_sql = format!(
        r#"
        UPDATE service_framework.service_registry
        SET
            state = $2::service_framework.service_state,
            last_heartbeat_at = $3
        WHERE service_id = $1
        RETURNING {SELECT_COLUMNS}
        "#
    );

    let maybe_record = sqlx::query_as::<_, ServiceRecord>(&update_sql)
        .bind(service_id)
        .bind(state_db)
        .bind(observed_at)
        .fetch_optional(&mut *tx)
        .await?;

    let record =
        maybe_record.ok_or_else(|| Error::NotFound(format!("service {service_id}")))?;

    sqlx::query(
        r#"
        INSERT INTO service_framework.service_heartbeat_log (
            service_id,
            state,
            observed_at,
            payload
        )
        VALUES (
            $1,
            $2::service_framework.service_state,
            $3,
            $4
        )
        "#,
    )
    .bind(service_id)
    .bind(state_db)
    .bind(observed_at)
    .bind(&payload)
    .execute(&mut *tx)
    .await?;

    tx.commit().await?;

    Ok(record)
}

pub async fn get_service(
    pool: &PgPool,
    service_id: &str,
) -> Result<Option<ServiceRecord>, Error> {
    let sql = format!(
        r#"
        SELECT {SELECT_COLUMNS}
        FROM service_framework.service_registry
        WHERE service_id = $1
        "#
    );

    let record = sqlx::query_as::<_, ServiceRecord>(&sql)
        .bind(service_id)
        .fetch_optional(pool)
        .await?;

    Ok(record)
}

pub async fn list_services(
    pool: &PgPool,
    environment: Option<String>,
    plane: Option<String>,
    limit: i64,
    offset: i64,
) -> Result<(Vec<ServiceRecord>, i64), Error> {
    let mut select = QueryBuilder::new(format!(
        "SELECT {SELECT_COLUMNS} FROM service_framework.service_registry WHERE 1=1"
    ));

    let mut count = QueryBuilder::new(
        "SELECT COUNT(*) FROM service_framework.service_registry WHERE 1=1",
    );

    if let Some(environment) = environment {
        select
            .push(" AND environment = ")
            .push_bind(environment.clone());
        count.push(" AND environment = ").push_bind(environment);
    }

    if let Some(plane) = plane {
        select.push(" AND plane::text = ").push_bind(plane.clone());
        count.push(" AND plane::text = ").push_bind(plane);
    }

    let total = count
        .build_query_scalar::<i64>()
        .fetch_one(pool)
        .await?;

    select
        .push(" ORDER BY service_name ASC, service_id ASC LIMIT ")
        .push_bind(limit)
        .push(" OFFSET ")
        .push_bind(offset);

    let services = select
        .build_query_as::<ServiceRecord>()
        .fetch_all(pool)
        .await?;

    Ok((services, total))
}

pub fn record_to_descriptor(record: &ServiceRecord) -> Result<ServiceDescriptor, Error> {
    let capabilities: Vec<String> = serde_json::from_value(record.capabilities.clone())?;
    let permissions: Vec<String> = serde_json::from_value(record.permissions.clone())?;
    let dependencies: Vec<String> = serde_json::from_value(record.dependencies.clone())?;

    let endpoint_jsons: Vec<EndpointJson> =
        serde_json::from_value(record.endpoints.clone())?;

    let endpoints = endpoint_jsons
        .into_iter()
        .map(|endpoint| ServiceEndpoint {
            name: endpoint.name,
            protocol: endpoint.protocol,
            uri: endpoint.uri,
            port: endpoint.port,
        })
        .collect();

    Ok(ServiceDescriptor {
        service_id: record.service_id.clone(),
        service_name: record.service_name.clone(),
        version: record.version.clone(),
        environment: record.environment.clone(),
        plane: validation::plane_from_db(&record.plane),
        fail_closed_policy: validation::policy_from_db(&record.fail_closed_policy),
        description: record.description.clone(),
        capabilities,
        permissions,
        endpoints,
        dependencies,
    })
}