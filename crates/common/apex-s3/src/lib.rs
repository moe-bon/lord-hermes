pub mod config;
pub mod errors;
pub mod models;

pub use config::S3Config;
pub use errors::S3Error;
pub use models::{BucketPurpose, BucketSpec, ObjectReference};

use aws_sdk_s3::primitives::ByteStream;
use aws_sdk_s3::Client;

pub struct S3Client {
    client: Client,
}

impl S3Client {
    pub async fn new(config: &S3Config) -> Result<Self, S3Error> {
        let sdk_config = aws_config::from_env()
            .endpoint_url(&config.endpoint_url)
            .region(aws_types::region::Region::new(config.region.clone()))
            .load()
            .await;

        let s3_config = aws_sdk_s3::config::Builder::from(&sdk_config)
            .force_path_style(config.force_path_style)
            .build();

        Ok(Self {
            client: Client::from_conf(s3_config),
        })
    }

    pub async fn upload_object(
        &self,
        bucket: &str,
        key: &str,
        data: Vec<u8>,
        content_type: &str,
    ) -> Result<ObjectReference, S3Error> {
        let size_bytes = data.len() as i64;
        
        let result = self
            .client
            .put_object()
            .bucket(bucket)
            .key(key)
            .content_type(content_type)
            .body(ByteStream::from(data))
            .send()
            .await
            .map_err(|e| S3Error::UploadFailed(e.to_string()))?;

        Ok(ObjectReference {
            bucket_name: bucket.to_string(),
            object_key: key.to_string(),
            version_id: result.version_id,
            content_type: content_type.to_string(),
            size_bytes,
            checksum_sha256: None,
        })
    }

    pub async fn download_object(
        &self,
        bucket: &str,
        key: &str,
        version_id: Option<&str>,
    ) -> Result<Vec<u8>, S3Error> {
        let mut req = self.client.get_object().bucket(bucket).key(key);
        
        if let Some(vid) = version_id {
            req = req.version_id(vid);
        }

        let result = req.send().await.map_err(|e| S3Error::DownloadFailed(e.to_string()))?;
        
        let bytes = result
            .body
            .collect()
            .await
            .map_err(|e| S3Error::DownloadFailed(e.to_string()))?
            .into_bytes()
            .to_vec();

        Ok(bytes)
    }
}