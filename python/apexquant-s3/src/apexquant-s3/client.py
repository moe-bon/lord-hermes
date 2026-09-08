from __future__ import annotations

import hashlib
from typing import BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from apexquant_s3.config import S3Settings
from apexquant_s3.models import BucketSpec, ObjectReference


class ObjectStorageError(Exception):
    pass


class ObjectStorageClient:
    def __init__(self, settings: S3Settings) -> None:
        self._settings = settings
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint_url,
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key,
            region_name=settings.region,
            config=Config(
                s3={"addressing_style": "path" if settings.force_path_style else "virtual"},
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    def ensure_bucket(self, spec: BucketSpec) -> None:
        try:
            self._client.head_bucket(Bucket=spec.name)
        except ClientError as exc:
            error_code = int(exc.response["Error"]["Code"])
            if error_code == 404:
                self._client.create_bucket(Bucket=spec.name)
            else:
                raise ObjectStorageError(f"failed to verify bucket {spec.name}") from exc

        if spec.versioning_enabled:
            self._client.put_bucket_versioning(
                Bucket=spec.name,
                VersioningConfiguration={"Status": "Enabled"},
            )

        if spec.lifecycle_expiration_days is not None:
            self._client.put_bucket_lifecycle_configuration(
                Bucket=spec.name,
                LifecycleConfiguration={
                    "Rules": [
                        {
                            "ID": "apex-expiration",
                            "Status": "Enabled",
                            "Filter": {"Prefix": ""},
                            "Expiration": {"Days": spec.lifecycle_expiration_days},
                        }
                    ]
                },
            )

    def upload_object(
        self,
        bucket_name: str,
        object_key: str,
        body: BinaryIO,
        content_type: str,
    ) -> ObjectReference:
        sha256 = hashlib.sha256()
        body.seek(0)
        for chunk in iter(lambda: body.read(8192), b""):
            sha256.update(chunk)
        body.seek(0)

        checksum = sha256.hexdigest()

        response = self._client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=body,
            ContentType=content_type,
            ChecksumAlgorithm="SHA256",
            ChecksumSHA256=checksum,
        )

        size_bytes = body.seek(0, 2)

        return ObjectReference(
            bucket_name=bucket_name,
            object_key=object_key,
            version_id=response.get("VersionId"),
            content_type=content_type,
            size_bytes=size_bytes,
            checksum_sha256=checksum,
        )

    def download_object(
        self,
        bucket_name: str,
        object_key: str,
        version_id: str | None = None,
    ) -> bytes:
        kwargs = {"Bucket": bucket_name, "Key": object_key}
        if version_id:
            kwargs["VersionId"] = version_id

        response = self._client.get_object(**kwargs)
        return response["Body"].read()

    def list_buckets(self) -> list[str]:
        response = self._client.list_buckets()
        return [bucket["Name"] for bucket in response.get("Buckets", [])]