use crate::errors::S3Error;

#[derive(Debug, Clone)]
pub struct S3Config {
    pub endpoint_url: String,
    pub region: String,
    pub force_path_style: bool,
}

impl S3Config {
    pub fn from_env() -> Result<Self, S3Error> {
        let endpoint_url = std::env::var("APEX_S3_ENDPOINT_URL")
            .unwrap_or_else(|_| "http://localhost:9000".to_string());
            
        let region = std::env::var("APEX_S3_REGION")
            .unwrap_or_else(|_| "us-east-1".to_string());
            
        let force_path_style = std::env::var("APEX_S3_FORCE_PATH_STYLE")
            .map(|v| v == "true" || v == "1")
            .unwrap_or(true);

        Ok(Self {
            endpoint_url,
            region,
            force_path_style,
        })
    }
}