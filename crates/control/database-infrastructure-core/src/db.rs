use crate::errors::Error;
use chrono::{DateTime, Utc};
use serde::Serialize;
use serde_json::{json, Value};
use sqlx::{PgPool, Row};
use std::collections::HashSet;

pub const REQUIRED_SCHEMAS: &[&str] = &[
    "service_framework",
    "container_policy",
    "config_management",
    "secrets_management",
    "database_infrastructure",
    "market_data",
    "broker",
    "orders",
    "execution",
    "positions",
    "reconciliation",
    "risk",
    "ledger",
    "strategy",
    "features",
    "models",
    "portfolio",
    "knowledge",
    "observability",
    "reporting",
];

pub const REQUIRED_EXTENSIONS: &[&str] = &["plpgsql"];

pub const RECOMMENDED_EXTENSIONS: &[&str] = &["pgcrypto", "pg_trgm", "btree_gist"];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum CheckStatus {
    PASS,
    WARN,
    FAIL,
}

#[derive(Debug, Serialize)]
pub struct CheckResult {
    pub name: String,
    pub status: CheckStatus,
    pub message: String,
    pub details: Value,
}

#[derive(Debug, Serialize)]
pub struct DatabaseReport {
    pub instance_name: String,
    pub environment: String,
    pub generated_at: DateTime<Utc>,
    pub ok: bool,
    pub errors_count: usize,
    pub warnings_count: usize,
    pub server_version: String,
    pub server_version_num: i32,
    pub current_database: String,
    pub current_user: String,
    pub max_connections: i32,
    pub extensions: Vec<String>,
    pub schemas: Vec<String>,
    pub required_schemas: Vec<String>,
    pub missing_schemas: Vec<String>,
    pub checks: Vec<CheckResult>,
}

pub async fn run_checks(
    pool: &PgPool,
    environment: &str,
    instance_name: &str,
) -> Result<DatabaseReport, Error> {
    let started_at = Utc::now();

    let (server_version_num,): (i32,) =
        sqlx::query_as("SELECT current_setting('server_version_num')::int")
            .fetch_one(pool)
            .await?;

    let (server_version,): (String,) = sqlx::query_as("SELECT version()")
        .fetch_one(pool)
        .await?;

    let (current_database,): (String,) = sqlx::query_as("SELECT current_database()")
        .fetch_one(pool)
        .await?;

    let (current_user,): (String,) = sqlx::query_as("SELECT current_user")
        .fetch_one(pool)
        .await?;

    let (max_connections,): (i32,) =
        sqlx::query_as("SELECT current_setting('max_connections')::int")
            .fetch_one(pool)
            .await?;

    let extension_rows: Vec<(String,)> =
        sqlx::query_as("SELECT extname FROM pg_extension ORDER BY extname")
            .fetch_all(pool)
            .await?;

    let schema_rows: Vec<(String,)> = sqlx::query_as(
        r#"
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name NOT IN ('pg_catalog', 'information_schema')
          AND schema_name NOT LIKE 'pg_%'
        ORDER BY schema_name
        "#,
    )
    .fetch_all(pool)
    .await?;

    let extensions: Vec<String> = extension_rows.into_iter().map(|row| row.0).collect();
    let schemas: Vec<String> = schema_rows.into_iter().map(|row| row.0).collect();

    let extension_set: HashSet<String> = extensions.iter().cloned().collect();
    let schema_set: HashSet<String> = schemas.iter().cloned().collect();

    let mut checks: Vec<CheckResult> = Vec::new();

    checks.push(check_version(server_version_num));
    checks.push(check_max_connections(max_connections));

    let mut extension_checks = check_extensions(&extension_set);
    checks.append(&mut extension_checks);

    let (schema_check, missing_schemas) = check_required_schemas(&schema_set);
    checks.push(schema_check);

    let errors_count = checks
        .iter()
        .filter(|check| check.status == CheckStatus::FAIL)
        .count();

    let warnings_count = checks
        .iter()
        .filter(|check| check.status == CheckStatus::WARN)
        .count();

    let ok = errors_count == 0;

    let completed_at = Utc::now();

    tracing::info!(
        instance_name = %instance_name,
        environment = %environment,
        ok = ok,
        errors = errors_count,
        warnings = warnings_count,
        started_at = %started_at,
        completed_at = %completed_at,
        "database infrastructure verification completed"
    );

    Ok(DatabaseReport {
        instance_name: instance_name.to_string(),
        environment: environment.to_string(),
        generated_at: completed_at,
        ok,
        errors_count,
        warnings_count,
        server_version,
        server_version_num,
        current_database,
        current_user,
        max_connections,
        extensions,
        schemas,
        required_schemas: REQUIRED_SCHEMAS.iter().map(|value| value.to_string()).collect(),
        missing_schemas,
        checks,
    })
}

pub async fn persist_report(pool: &PgPool, report: &DatabaseReport) -> Result<String, Error> {
    let (run_id,): (String,) = sqlx::query_as("SELECT gen_random_uuid()::text")
        .fetch_one(pool)
        .await?;

    let report_json = serde_json::to_value(report)?;

    let mut tx = pool.begin().await?;

    sqlx::query(
        r#"
        INSERT INTO database_infrastructure.verification_runs (
            run_id,
            instance_name,
            environment,
            started_at,
            completed_at,
            ok,
            errors_count,
            warnings_count,
            report
        )
        VALUES (
            $1,
            $2,
            $3,
            $4,
            $5,
            $6,
            $7,
            $8,
            $9
        )
        "#,
    )
    .bind(&run_id)
    .bind(&report.instance_name)
    .bind(&report.environment)
    .bind(report.generated_at)
    .bind(report.generated_at)
    .bind(report.ok)
    .bind(report.errors_count as i32)
    .bind(report.warnings_count as i32)
    .bind(&report_json)
    .execute(&mut *tx)
    .await?;

    for check in &report.checks {
        let status = match check.status {
            CheckStatus::PASS => "PASS",
            CheckStatus::WARN => "WARN",
            CheckStatus::FAIL => "FAIL",
        };

        sqlx::query(
            r#"
            INSERT INTO database_infrastructure.verification_checks (
                run_id,
                check_name,
                status,
                message,
                details
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                $5
            )
            "#,
        )
        .bind(&run_id)
        .bind(&check.name)
        .bind(status)
        .bind(&check.message)
        .bind(&check.details)
        .execute(&mut *tx)
        .await?;
    }

    tx.commit().await?;

    Ok(run_id)
}

pub fn check_version(server_version_num: i32) -> CheckResult {
    if server_version_num >= 160_000 {
        CheckResult {
            name: "postgres_version".to_string(),
            status: CheckStatus::PASS,
            message: "PostgreSQL major version is supported".to_string(),
            details: json!({
                "server_version_num": server_version_num,
                "minimum_required": 160_000
            }),
        }
    } else {
        CheckResult {
            name: "postgres_version".to_string(),
            status: CheckStatus::FAIL,
            message: "PostgreSQL 16 or newer is required".to_string(),
            details: json!({
                "server_version_num": server_version_num,
                "minimum_required": 160_000
            }),
        }
    }
}

pub fn check_max_connections(max_connections: i32) -> CheckResult {
    if max_connections < 100 {
        CheckResult {
            name: "max_connections".to_string(),
            status: CheckStatus::WARN,
            message: "max_connections is below the recommended minimum of 100".to_string(),
            details: json!({
                "max_connections": max_connections,
                "recommended_minimum": 100
            }),
        }
    } else {
        CheckResult {
            name: "max_connections".to_string(),
            status: CheckStatus::PASS,
            message: "max_connections is sufficient".to_string(),
            details: json!({
                "max_connections": max_connections,
                "recommended_minimum": 100
            }),
        }
    }
}

pub fn check_extensions(existing: &HashSet<String>) -> Vec<CheckResult> {
    let mut checks = Vec::new();

    for required in REQUIRED_EXTENSIONS {
        if existing.contains(*required) {
            checks.push(CheckResult {
                name: format!("extension_{required}"),
                status: CheckStatus::PASS,
                message: format!("required extension {required} is installed"),
                details: json!({
                    "extension": required,
                    "requirement": "required"
                }),
            });
        } else {
            checks.push(CheckResult {
                name: format!("extension_{required}"),
                status: CheckStatus::FAIL,
                message: format!("required extension {required} is missing"),
                details: json!({
                    "extension": required,
                    "requirement": "required"
                }),
            });
        }
    }

    for recommended in RECOMMENDED_EXTENSIONS {
        if existing.contains(*recommended) {
            checks.push(CheckResult {
                name: format!("extension_{recommended}"),
                status: CheckStatus::PASS,
                message: format!("recommended extension {recommended} is installed"),
                details: json!({
                    "extension": recommended,
                    "requirement": "recommended"
                }),
            });
        } else {
            checks.push(CheckResult {
                name: format!("extension_{recommended}"),
                status: CheckStatus::WARN,
                message: format!("recommended extension {recommended} is missing"),
                details: json!({
                    "extension": recommended,
                    "requirement": "recommended"
                }),
            });
        }
    }

    checks
}

pub fn check_required_schemas(existing: &HashSet<String>) -> (CheckResult, Vec<String>) {
    let missing: Vec<String> = REQUIRED_SCHEMAS
        .iter()
        .filter(|schema| !existing.contains(**schema))
        .map(|schema| schema.to_string())
        .collect();

    if missing.is_empty() {
        (
            CheckResult {
                name: "required_schemas".to_string(),
                status: CheckStatus::PASS,
                message: "all required schemas exist".to_string(),
                details: json!({
                    "required_schemas": REQUIRED_SCHEMAS,
                    "missing_schemas": []
                }),
            },
            missing,
        )
    } else {
        (
            CheckResult {
                name: "required_schemas".to_string(),
                status: CheckStatus::FAIL,
                message: "one or more required schemas are missing".to_string(),
                details: json!({
                    "required_schemas": REQUIRED_SCHEMAS,
                    "missing_schemas": missing
                }),
            },
            missing,
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn version_check_passes_for_postgres_16() {
        let check = check_version(160_000);

        assert_eq!(check.status, CheckStatus::PASS);
    }

    #[test]
    fn version_check_fails_for_postgres_15() {
        let check = check_version(150_000);

        assert_eq!(check.status, CheckStatus::FAIL);
    }

    #[test]
    fn max_connections_warns_below_recommended() {
        let check = check_max_connections(50);

        assert_eq!(check.status, CheckStatus::WARN);
    }

    #[test]
    fn max_connections_passes_at_recommended() {
        let check = check_max_connections(100);

        assert_eq!(check.status, CheckStatus::PASS);
    }

    #[test]
    fn missing_required_schema_is_detected() {
        let existing = HashSet::from(["database_infrastructure".to_string()]);

        let (check, missing) = check_required_schemas(&existing);

        assert_eq!(check.status, CheckStatus::FAIL);
        assert!(missing.contains(&"market_data".to_string()));
    }

    #[test]
    fn all_required_schemas_pass() {
        let existing: HashSet<String> =
            REQUIRED_SCHEMAS.iter().map(|schema| schema.to_string()).collect();

        let (check, missing) = check_required_schemas(&existing);

        assert_eq!(check.status, CheckStatus::PASS);
        assert!(missing.is_empty());
    }
}