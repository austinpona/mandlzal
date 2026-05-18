"""Pluggable photo storage for field-capture ID photos."""
from __future__ import annotations

import uuid
from pathlib import Path, PurePosixPath
from typing import Protocol


class PhotoStorage(Protocol):
    def save(self, blob: bytes, ext: str) -> str: ...
    def load(self, path: str) -> bytes: ...
    def delete(self, path: str) -> None: ...


class FilesystemPhotoStorage:
    """Store photos under <root>/id_photos/<uuid>.<ext>."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        (self.root / "id_photos").mkdir(parents=True, exist_ok=True)

    def save(self, blob: bytes, ext: str) -> str:
        suffix = ext.lstrip(".").lower()
        name = f"{uuid.uuid4()}.{suffix}"
        rel = f"id_photos/{name}"
        (self.root / rel).write_bytes(blob)
        return rel

    def load(self, path: str) -> bytes:
        return (self.root / path).read_bytes()

    def delete(self, path: str) -> None:
        p = self.root / path
        if p.exists():
            p.unlink()


class S3PhotoStorage:
    """Store photos in an S3-compatible bucket.

    The returned path is the object key, so customers keep a portable
    reference regardless of which S3-compatible service backs the bucket.
    """

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "id_photos",
        region_name: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        if not bucket:
            raise ValueError("PHOTO_STORAGE_S3_BUCKET is required when PHOTO_STORAGE_BACKEND=s3")
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required for PHOTO_STORAGE_BACKEND=s3") from exc

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = boto3.client(
            "s3",
            region_name=region_name or None,
            endpoint_url=endpoint_url or None,
        )

    def _key(self, ext: str) -> str:
        suffix = ext.lstrip(".").lower()
        return f"{self.prefix}/{uuid.uuid4()}.{suffix}"

    def save(self, blob: bytes, ext: str) -> str:
        key = self._key(ext)
        content_type = "image/png" if ext.lstrip(".").lower() == "png" else "image/jpeg"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=blob, ContentType=content_type)
        return key

    def load(self, path: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=path)
        return obj["Body"].read()

    def delete(self, path: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=path)


def get_photo_storage() -> PhotoStorage:
    """Build the storage adapter from current settings.

    The settings object is read lazily so tests can clear the settings cache
    after monkeypatching environment variables.
    """
    from app.config import get_settings

    s = get_settings()
    if s.PHOTO_STORAGE_BACKEND == "filesystem":
        return FilesystemPhotoStorage(root=s.PHOTO_STORAGE_PATH)
    if s.PHOTO_STORAGE_BACKEND == "s3":
        return S3PhotoStorage(
            bucket=s.PHOTO_STORAGE_S3_BUCKET,
            prefix=s.PHOTO_STORAGE_S3_PREFIX,
            region_name=s.PHOTO_STORAGE_S3_REGION,
            endpoint_url=s.PHOTO_STORAGE_S3_ENDPOINT_URL,
        )
    raise ValueError(f"Unknown PHOTO_STORAGE_BACKEND: {s.PHOTO_STORAGE_BACKEND!r}")


def _clean_relative_path(value: str) -> str | None:
    normalized = value.replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or any(part == ".." for part in path.parts):
        return None
    return normalized


def _safe_filesystem_path(root: Path, rel_path: str) -> Path | None:
    root_resolved = root.resolve()
    target = (root / rel_path).resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError:
        return None
    return target


def resolve_photo_path(id_photo_id: str) -> str | None:
    """Resolve an uploaded photo id back to its relative storage path."""
    from app.config import get_settings

    settings = get_settings()

    if "/" in id_photo_id or "\\" in id_photo_id:
        rel_path = _clean_relative_path(id_photo_id)
        if rel_path is None:
            return None
        if settings.PHOTO_STORAGE_BACKEND == "filesystem":
            target = _safe_filesystem_path(Path(settings.PHOTO_STORAGE_PATH), rel_path)
            return rel_path if target is not None and target.exists() else None
        if settings.PHOTO_STORAGE_BACKEND == "s3":
            prefix = settings.PHOTO_STORAGE_S3_PREFIX.strip("/")
            if prefix and not rel_path.startswith(f"{prefix}/"):
                return None
            return rel_path
        return None

    root = Path(settings.PHOTO_STORAGE_PATH) / "id_photos"
    if not root.exists():
        return None
    matches = sorted(root.glob(f"{id_photo_id}.*"))
    if not matches:
        return None
    return f"id_photos/{matches[0].name}"
