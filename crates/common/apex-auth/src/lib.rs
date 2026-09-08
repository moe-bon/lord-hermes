use base64::{engine::general_purpose, Engine as _};
use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use thiserror::Error;

type HmacSha256 = Hmac<Sha256>;

const TOKEN_VERSION: &str = "v1";

#[derive(Debug, Error)]
pub enum AuthError {
    #[error("invalid token format")]
    InvalidTokenFormat,

    #[error("invalid token version")]
    InvalidTokenVersion,

    #[error("invalid base64 payload")]
    InvalidBase64,

    #[error("invalid token payload")]
    InvalidPayload,

    #[error("invalid token signature")]
    InvalidSignature,

    #[error("token expired")]
    TokenExpired,

    #[error("invalid secret")]
    InvalidSecret,

    #[error("internal authentication error")]
    Internal,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenClaims {
    pub sub: String,
    pub typ: String,
    pub iat: i64,
    pub exp: i64,
    pub jti: String,
    pub permissions: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct AuthContext {
    pub subject: String,
    pub principal_type: String,
    pub permissions: Vec<String>,
    pub expires_at: i64,
    pub jti: String,
}

pub fn decode_secret_b64(secret_b64: &str) -> Result<Vec<u8>, AuthError> {
    let secret = general_purpose::STANDARD
        .decode(secret_b64.trim())
        .map_err(|_| AuthError::InvalidSecret)?;

    if secret.len() != 32 {
        return Err(AuthError::InvalidSecret);
    }

    Ok(secret)
}

pub fn now_unix() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .expect("system clock before UNIX epoch")
        .as_secs() as i64
}

pub fn sign_token(
    secret: &[u8],
    claims: &TokenClaims,
) -> Result<String, AuthError> {
    let payload_json =
        serde_json::to_vec(claims).map_err(|_| AuthError::Internal)?;

    let payload_b64 = general_purpose::URL_SAFE_NO_PAD.encode(payload_json);

    let signing_input = format!("{TOKEN_VERSION}.{payload_b64}");

    let mut mac =
        HmacSha256::new_from_slice(secret).map_err(|_| AuthError::InvalidSecret)?;

    mac.update(signing_input.as_bytes());

    let signature = mac.finalize().into_bytes();
    let signature_b64 = general_purpose::URL_SAFE_NO_PAD.encode(signature);

    Ok(format!("{signing_input}.{signature_b64}"))
}

pub fn verify_token(
    secret: &[u8],
    token: &str,
    now: i64,
) -> Result<AuthContext, AuthError> {
    let parts: Vec<&str> = token.trim().split('.').collect();

    if parts.len() != 3 {
        return Err(AuthError::InvalidTokenFormat);
    }

    let version = parts[0];
    let payload_b64 = parts[1];
    let signature_b64 = parts[2];

    if version != TOKEN_VERSION {
        return Err(AuthError::InvalidTokenVersion);
    }

    let payload_bytes = general_purpose::URL_SAFE_NO_PAD
        .decode(payload_b64)
        .map_err(|_| AuthError::InvalidBase64)?;

    let signature = general_purpose::URL_SAFE_NO_PAD
        .decode(signature_b64)
        .map_err(|_| AuthError::InvalidBase64)?;

    let signing_input = format!("{version}.{payload_b64}");

    let mut mac =
        HmacSha256::new_from_slice(secret).map_err(|_| AuthError::InvalidSecret)?;

    mac.update(signing_input.as_bytes());

    mac.verify_slice(&signature)
        .map_err(|_| AuthError::InvalidSignature)?;

    let claims: TokenClaims =
        serde_json::from_slice(&payload_bytes).map_err(|_| AuthError::InvalidPayload)?;

    if claims.exp <= now {
        return Err(AuthError::TokenExpired);
    }

    Ok(AuthContext {
        subject: claims.sub,
        principal_type: claims.typ,
        permissions: claims.permissions,
        expires_at: claims.exp,
        jti: claims.jti,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_secret() -> Vec<u8> {
        vec![7u8; 32]
    }

    fn test_claims(exp: i64) -> TokenClaims {
        TokenClaims {
            sub: "bootstrap-admin".to_string(),
            typ: "ADMIN".to_string(),
            iat: 1_000,
            exp,
            jti: "test-jti".to_string(),
            permissions: vec!["*".to_string()],
        }
    }

    #[test]
    fn token_roundtrip_passes() {
        let secret = test_secret();
        let claims = test_claims(2_000);

        let token = sign_token(&secret, &claims).expect("token should sign");

        let context = verify_token(&secret, &token, 1_500)
            .expect("token should verify");

        assert_eq!(context.subject, "bootstrap-admin");
        assert_eq!(context.principal_type, "ADMIN");
        assert_eq!(context.permissions, vec!["*".to_string()]);
    }

    #[test]
    fn expired_token_is_rejected() {
        let secret = test_secret();
        let claims = test_claims(1_000);

        let token = sign_token(&secret, &claims).expect("token should sign");

        let result = verify_token(&secret, &token, 2_000);

        assert!(matches!(result, Err(AuthError::TokenExpired)));
    }

    #[test]
    fn tampered_token_is_rejected() {
        let secret = test_secret();
        let claims = test_claims(2_000);

        let token = sign_token(&secret, &claims).expect("token should sign");

        let mut parts: Vec<&str> = token.split('.').collect();
        let payload = parts[1].to_string();
        let signature = parts[2].to_string();

        let tampered = format!("v1.{}x.{}", payload, signature);

        let result = verify_token(&secret, &tampered, 1_500);

        assert!(matches!(
            result,
            Err(AuthError::InvalidBase64 | AuthError::InvalidSignature)
        ));
    }

    #[test]
    fn wrong_secret_is_rejected() {
        let secret = test_secret();
        let wrong_secret = vec![9u8; 32];
        let claims = test_claims(2_000);

        let token = sign_token(&secret, &claims).expect("token should sign");

        let result = verify_token(&wrong_secret, &token, 1_500);

        assert!(matches!(result, Err(AuthError::InvalidSignature)));
    }
}