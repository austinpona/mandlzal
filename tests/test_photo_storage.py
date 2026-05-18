"""Tests for the filesystem-backed photo storage adapter."""
import pytest

from app.services.photo_storage import (
    FilesystemPhotoStorage,
    S3PhotoStorage,
    get_photo_storage,
    resolve_photo_path,
)


def test_filesystem_save_writes_file_and_returns_path(tmp_path):
    storage = FilesystemPhotoStorage(root=tmp_path)
    blob = b"\xff\xd8\xff" + b"x" * 100
    path = storage.save(blob, ext="jpg")
    assert path.startswith("id_photos/")
    assert path.endswith(".jpg")
    assert (tmp_path / path).read_bytes() == blob


def test_filesystem_load_returns_bytes(tmp_path):
    storage = FilesystemPhotoStorage(root=tmp_path)
    blob = b"hello"
    path = storage.save(blob, ext="jpg")
    assert storage.load(path) == blob


def test_filesystem_delete_removes_file(tmp_path):
    storage = FilesystemPhotoStorage(root=tmp_path)
    path = storage.save(b"x", ext="jpg")
    storage.delete(path)
    assert not (tmp_path / path).exists()


def test_get_photo_storage_returns_filesystem_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("PHOTO_STORAGE_BACKEND", "filesystem")
    monkeypatch.setenv("PHOTO_STORAGE_PATH", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    storage = get_photo_storage()
    assert isinstance(storage, FilesystemPhotoStorage)


def test_get_photo_storage_raises_for_unknown_backend(monkeypatch):
    monkeypatch.setenv("PHOTO_STORAGE_BACKEND", "azure_blob")
    from app.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(ValueError, match="Unknown PHOTO_STORAGE_BACKEND"):
        get_photo_storage()


def test_s3_storage_requires_bucket():
    with pytest.raises(ValueError, match="PHOTO_STORAGE_S3_BUCKET"):
        S3PhotoStorage(bucket="")


def test_resolve_photo_path_accepts_existing_filesystem_path(monkeypatch, tmp_path):
    monkeypatch.setenv("PHOTO_STORAGE_BACKEND", "filesystem")
    monkeypatch.setenv("PHOTO_STORAGE_PATH", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        path = FilesystemPhotoStorage(root=tmp_path).save(b"x", ext="jpg")
        assert resolve_photo_path(path) == path
        assert resolve_photo_path("../secret.jpg") is None
        assert resolve_photo_path("id_photos/missing.jpg") is None
    finally:
        get_settings.cache_clear()


def test_resolve_photo_path_accepts_s3_prefixed_path(monkeypatch):
    monkeypatch.setenv("PHOTO_STORAGE_BACKEND", "s3")
    monkeypatch.setenv("PHOTO_STORAGE_S3_PREFIX", "id_photos")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        assert resolve_photo_path("id_photos/abc.jpg") == "id_photos/abc.jpg"
        assert resolve_photo_path("other/abc.jpg") is None
    finally:
        get_settings.cache_clear()
