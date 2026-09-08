from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol

import boto3
from botocore.exceptions import ClientError

from apexquant_backup_recovery.errors import BackupError


class ObjectStorageError(BackupError):
    pass


class ObjectStorageClient(Protocol):
    def upload_file(self, local_path: Path, key: str) -> str:
        raise NotImplementedError

    def download_file(self, key: str, local_path: Path) -> None:
        raise NotImplementedError

    def list_objects(self, prefix: str = "") -> list[str]:
        raise NotImplementedError

    def delete_object(self, key: str) -> None:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError


class LocalDirectoryStorage:
    def __init__(self, root: Path, bucket: str) -> None:
        self._root = Path(root)
        self._bucket = bucket
        self._base = self._root / bucket

        self._base.mkdir(parents=True, exist_ok=True)

    def _path_for_key(self, key: str) -> Path:
        path = self._base / key
        path.parent.mkdir(parents=True, exist_ok=True)

        return path

    def upload_file(self, local_path: Path, key: str) -> str:
        target = self._path_for_key(key)

        shutil.copyfile(local_path, target)

        return target.as_uri()

    def download_file(self, key: str, local_path: Path) -> None:
        source = self._base / key

        if not source.exists():
            raise ObjectStorageError(f"backup object does not exist: {key}")

        local_path.parent.mkdir(parents=True, exist_ok=True)

        shutil.copyfile(source, local_path)

    def list_objects(self, prefix: str = "") -> list[str]:
        if not self._base.exists():
            return []

        keys: list[str] = []

        for path in self._base.rglob("*"):
            if path.is_file():
                key = path.relative_to(self._base).as_posix()

                if key.startswith(prefix):
                    keys.append(key)

        return sorted(keys)

    def delete_object(self, key: str) -> None:
        path = self._base / key

        if path.exists():
            path.unlink()

    def exists(self, key: str) -> bool:
        return (self._base / key).exists()


class S3Storage:
    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        region_name: str | None = None,
        server_side_encryption: bool = False,
    ) -> None:
        self._bucket = bucket
        self._server_side_encryption = server_side_encryption

        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region_name,
        )

    def upload_file(self, local_path: Path, key: str) -> str:
        extra_args = {}

        if self._server_side_encryption:
            extra_args["ServerSideEncryption"] = "AES256"

        self._client.upload_file(
            str(local_path),
            self._bucket,
            key,
            ExtraArgs=extra_args or None,
        )

        return f"s3://{self._bucket}/{key}"

    def download_file(self, key: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)

        self._client.download_file(self._bucket, key, str(local_path))

    def list_objects(self, prefix: str = "") -> list[str]:
        keys: list[str] = []

        paginator = self._client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                keys.append(item["Key"])

        return sorted(keys)

    def delete_object(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False