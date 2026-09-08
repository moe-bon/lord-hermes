use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum BucketPurpose {
    MarketDataRaw,
    ModelArtifacts,
    KnowledgeRaw,
    Backups,
    Temporary,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BucketSpec {
    pub name: String,
    pub purpose: BucketPurpose,
    pub versioning_enabled: bool,
    pub lifecycle_expiration_days: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ObjectReference {
    pub bucket_name: String,
    pub object_key: String,
    pub version_id: Option<String>,
    pub content_type: String,
    pub size_bytes: i64,
    pub checksum_sha256: Option<String>,
}