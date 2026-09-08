use crate::models::*;
use sqlx::PgPool;
use anyhow::Result;

pub struct SourceRepository { pub pool: PgPool }

impl SourceRepository {
    pub fn new(pool: PgPool) -> Self { Self { pool } }

    pub async fn upsert_source(&self, req: CreateSourceRequest) -> Result<Source> {
        let namespace = match req.tier {
            ProvenanceTier::T0 | ProvenanceTier::T1 => "production",
            ProvenanceTier::T2 | ProvenanceTier::T3 => "research",
        };
        let asset_classes_str: Vec<String> = req.asset_classes.iter().map(|a| format!("{:?}", a)).collect();

        let source = sqlx::query_as::<_, Source>(
            r#"
            INSERT INTO market_data.sources (
                source_id, name, tier, asset_classes, is_venue_native, 
                provides_sequence_ids, provides_l2_depth, namespace
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (source_id) DO UPDATE SET
                name = EXCLUDED.name, tier = EXCLUDED.tier, asset_classes = EXCLUDED.asset_classes,
                is_venue_native = EXCLUDED.is_venue_native, provides_sequence_ids = EXCLUDED.provides_sequence_ids,
                provides_l2_depth = EXCLUDED.provides_l2_depth, namespace = EXCLUDED.namespace, updated_at = now()
            RETURNING *
            "#
        )
        .bind(&req.source_id).bind(&req.name).bind(req.tier).bind(&asset_classes_str)
        .bind(req.is_venue_native).bind(req.provides_sequence_ids).bind(req.provides_l2_depth).bind(namespace)
        .fetch_one(&self.pool).await?;
        Ok(source)
    }

    pub async fn assign_role(&self, req: AssignRoleRequest) -> Result<()> {
        if req.role == SourceRole::CANONICAL && req.priority != 1 {
            anyhow::bail!("Law #5 Violation: CANONICAL source must have priority 1.");
        }
        let ac_str = format!("{:?}", req.asset_class);
        sqlx::query(
            r#"
            INSERT INTO market_data.source_assignments (source_id, asset_class, data_type, role, priority)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (source_id, asset_class, data_type, role) DO UPDATE SET priority = EXCLUDED.priority
            "#
        )
        .bind(&req.source_id).bind(&ac_str).bind(req.data_type).bind(req.role).bind(req.priority)
        .execute(&self.pool).await?;
        Ok(())
    }
}
