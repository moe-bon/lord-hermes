use crate::errors::RedisError;
use crate::pool::RedisPool;
use redis::AsyncCommands;
use std::time::Duration;
use uuid::Uuid;

const UNLOCK_SCRIPT: &str = r#"
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"#;

pub struct DistributedLock {
    pool: RedisPool,
    key: String,
    token: String,
    ttl: Duration,
    acquired: bool,
}

impl DistributedLock {
    pub fn new(pool: RedisPool, key: String, ttl: Duration) -> Self {
        Self {
            pool,
            key,
            token: Uuid::new_v4().to_string(),
            ttl,
            acquired: false,
        }
    }

    pub async fn acquire(&mut self) -> Result<bool, RedisError> {
        let mut conn = self.pool.manager();

        let result: Option<String> = redis::cmd("SET")
            .arg(&self.key)
            .arg(&self.token)
            .arg("NX")
            .arg("PX")
            .arg(self.ttl.as_millis() as u64)
            .query_async(&mut conn)
            .await?;

        self.acquired = result.is_some();
        Ok(self.acquired)
    }

    pub async fn release(&mut self) -> Result<bool, RedisError> {
        if !self.acquired {
            return Ok(false);
        }

        let mut conn = self.pool.manager();
        let script = redis::Script::new(UNLOCK_SCRIPT);

        let result: i32 = script
            .key(&self.key)
            .arg(&self.token)
            .invoke_async(&mut conn)
            .await?;

        self.acquired = false;
        Ok(result == 1)
    }
}

impl Drop for DistributedLock {
    fn drop(&mut self) {
        if self.acquired {
            tracing::warn!(
                key = %self.key,
                "distributed lock dropped while still acquired; relying on TTL for cleanup"
            );
        }
    }
}