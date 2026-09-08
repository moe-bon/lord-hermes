use thiserror::Error;

#[derive(Debug, Error)]
pub enum S3Error {
    #[error("configuration error: {0}")]
    Config(String),

    #[error("upload failed: {0}")]
    UploadFailed(String),

    #[error("download failed: {0}")]
    DownloadFailed(String),

    #[error("bucket not found: {0}")]
    BucketNotFound(String),
}