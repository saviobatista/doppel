from typing import Protocol

import anyio
import boto3
from botocore.exceptions import ClientError

from doppel_api.config import Settings


class Storage(Protocol):
    async def ensure_bucket(self) -> None: ...
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def presign_get(self, key: str, expires_in: int = 3600) -> str: ...


class MemoryStorage:
    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def ensure_bucket(self) -> None:
        return None

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self._objects[key] = data

    async def get(self, key: str) -> bytes:
        return self._objects[key]

    async def presign_get(self, key: str, expires_in: int = 3600) -> str:
        return f"memory://{key}"


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3", endpoint_url=settings.s3_endpoint, region_name=settings.s3_region
        )
        public = settings.s3_public_endpoint or settings.s3_endpoint
        self._presign_client = (
            self._client
            if public == settings.s3_endpoint
            else boto3.client("s3", endpoint_url=public, region_name=settings.s3_region)
        )

    async def ensure_bucket(self) -> None:
        def _ensure() -> None:
            try:
                self._client.head_bucket(Bucket=self._bucket)
            except ClientError as e:
                if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
                    self._client.create_bucket(Bucket=self._bucket)
                else:
                    raise

        await anyio.to_thread.run_sync(_ensure)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await anyio.to_thread.run_sync(
            lambda: self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        )

    async def get(self, key: str) -> bytes:
        def _get() -> bytes:
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

        return await anyio.to_thread.run_sync(_get)

    async def presign_get(self, key: str, expires_in: int = 3600) -> str:
        return self._presign_client.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=expires_in
        )
