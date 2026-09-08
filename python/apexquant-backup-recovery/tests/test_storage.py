from pathlib import Path

from apexquant_backup_recovery.storage import LocalDirectoryStorage


def test_local_storage_upload_download_list_delete(tmp_path: Path) -> None:
    storage = LocalDirectoryStorage(root=tmp_path, bucket="backups")

    source = tmp_path / "source.dump"
    source.write_bytes(b"backup-data")

    uri = storage.upload_file(source, "postgres/apexquant/run-1.dump")

    assert uri.startswith("file://")
    assert storage.exists("postgres/apexquant/run-1.dump")

    listed = storage.list_objects("postgres/")

    assert listed == ["postgres/apexquant/run-1.dump"]

    download_path = tmp_path / "download.dump"
    storage.download_file("postgres/apexquant/run-1.dump", download_path)

    assert download_path.read_bytes() == b"backup-data"

    storage.delete_object("postgres/apexquant/run-1.dump")

    assert not storage.exists("postgres/apexquant/run-1.dump")