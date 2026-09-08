import io
import pytest
from moto import mock_aws
import boto3

from apexquant_s3.client import ObjectStorageClient
from apexquant_s3.config import S3Settings
from apexquant_s3.models import BucketPurpose, BucketSpec
from apexquant_s3.registry import BucketRegistry


@pytest.fixture
def aws_credentials():
    import os
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def s3_client(aws_credentials):
    with mock_aws():
        settings = S3Settings(
            endpoint_url="http://localhost:5000",
            access_key_id="testing",
            secret_access_key="testing",
            region="us-east-1",
        )
        yield ObjectStorageClient(settings)


def test_ensure_bucket_creates_and_versions(s3_client: ObjectStorageClient) -> None:
    spec = BucketSpec(
        name="test-bucket",
        purpose=BucketPurpose.MODEL_ARTIFACTS,
        versioning_enabled=True,
    )
    
    s3_client.ensure_bucket(spec)
    
    buckets = s3_client.list_buckets()
    assert "test-bucket" in buckets


def test_upload_and_download_object(s3_client: ObjectStorageClient) -> None:
    spec = BucketSpec(
        name="test-bucket-2",
        purpose=BucketPurpose.TEMPORARY,
        lifecycle_expiration_days=7,
    )
    s3_client.ensure_bucket(spec)

    data = b"hello world"
    body = io.BytesIO(data)
    
    ref = s3_client.upload_object(
        bucket_name="test-bucket-2",
        object_key="test.txt",
        body=body,
        content_type="text/plain",
    )

    assert ref.size_bytes == 11
    assert ref.checksum_sha256 is not None

    downloaded = s3_client.download_object("test-bucket-2", "test.txt")
    assert downloaded == data


def test_registry_enforces_versioning_for_models() -> None:
    with pytest.raises(ValueError):
        BucketSpec(
            name="bad-models",
            purpose=BucketPurpose.MODEL_ARTIFACTS,
            versioning_enabled=False,
        )

def test_registry_enforces_lifecycle_for_temp() -> None:
    with pytest.raises(ValueError):
        BucketSpec(
            name="bad-temp",
            purpose=BucketPurpose.TEMPORARY,
            versioning_enabled=False,
            lifecycle_expiration_days=None,
        )