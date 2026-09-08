use database_infrastructure_core::db;
use sqlx::PgPool;

#[sqlx::test(migrations = "../../../migrations/postgres/database_infrastructure")]
async fn database_verification_passes(pool: PgPool) {
    let report = db::run_checks(&pool, "test", "test-instance")
        .await
        .expect("database verification should succeed");

    assert!(report.ok);
    assert_eq!(report.errors_count, 0);
    assert!(report.missing_schemas.is_empty());
    assert!(report.server_version_num >= 160_000);
}

#[sqlx::test(migrations = "../../../migrations/postgres/database_infrastructure")]
async fn database_verification_report_can_be_persisted(pool: PgPool) {
    let report = db::run_checks(&pool, "test", "test-instance")
        .await
        .expect("database verification should succeed");

    let run_id = db::persist_report(&pool, &report)
        .await
        .expect("verification report should persist");

    assert!(!run_id.is_empty());
}