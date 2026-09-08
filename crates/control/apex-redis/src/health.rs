use crate::errors::RedisError;
use crate::pool::RedisPool;
use redis::AsyncCommands;

pub async fn check_health(pool: &RedisPool) -> Result<bool, RedisError> {
    let mut conn = pool.manager();
    let result: String = redis::cmd("PING").query_async(&mut conn).await?;
    Ok(result == "PONG")
}

