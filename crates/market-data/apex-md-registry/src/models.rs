use serde::{Deserialize, Serialize};
use sqlx::FromRow;
use chrono::{DateTime, Utc};

#[derive(Debug, Serialize, Deserialize, Clone, Copy, PartialEq, Eq, sqlx::Type)]
#[sqlx(type_name = "market_data.provenance_tier", rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ProvenanceTier { T0, T1, T2, T3 }

#[derive(Debug, Serialize, Deserialize, Clone, Copy, PartialEq, Eq, sqlx::Type)]
#[sqlx(type_name = "market_data.source_role", rename_all = "SCREAMING_SNAKE_CASE")]
#[allow(non_camel_case_types)]
pub enum SourceRole { CANONICAL, VALIDATOR, FAILOVER, RESEARCH_ONLY }

#[derive(Debug, Serialize, Deserialize, Clone, Copy, PartialEq, Eq, sqlx::Type)]
#[sqlx(type_name = "market_data.data_type", rename_all = "SCREAMING_SNAKE_CASE")]
#[allow(non_camel_case_types)]
pub enum DataType { L1_TICK, L2_BOOK, OHLCV, TRADES, LIQUIDATIONS, METADATA }

#[derive(Debug, Serialize, Deserialize, Clone, Copy, PartialEq, Eq)]
#[allow(non_camel_case_types)]
pub enum AssetClass { CRYPTO, FX, EQUITY, FUTURE, INDEX, OPTION }

#[derive(Debug, Serialize, Deserialize, FromRow, Clone)]
pub struct Source {
    pub source_id: String,
    pub name: String,
    pub tier: ProvenanceTier,
    pub asset_classes: Vec<String>, 
    pub is_venue_native: bool,
    pub provides_sequence_ids: bool,
    pub provides_l2_depth: bool,
    pub namespace: String,
    pub trust_score: f64, 
    pub is_healthy: bool,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct CreateSourceRequest {
    pub source_id: String,
    pub name: String,
    pub tier: ProvenanceTier,
    pub asset_classes: Vec<AssetClass>,
    pub is_venue_native: bool,
    pub provides_sequence_ids: bool,
    pub provides_l2_depth: bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct AssignRoleRequest {
    pub source_id: String,
    pub asset_class: AssetClass,
    pub data_type: DataType,
    pub role: SourceRole,
    pub priority: i32,
}
