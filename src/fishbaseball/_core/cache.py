"""On-disk cache layout and metadata.

    <root>/
    ├── metadata.json                     # per source: {"etag": ..., "last_checked": iso}
    └── <source>/
        ├── latest.json
        ├── objects/                      # partitioned tables only, shared by every release
        │   └── <sha256>.parquet
        └── <tag>/
            ├── manifest.json
            └── <table>.parquet           # whole-file tables only

Only `metadata.json` is read-modify-written by potentially concurrent processes, so only it
is guarded by a file lock. Pointer, manifest and table files are written once per tag/table and
never mutated in place, so a plain atomic replace is enough for them.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import platformdirs
from filelock import FileLock

from fishbaseball import config

METADATA_FILE = "metadata.json"
POINTER_FILE = "latest.json"
MANIFEST_FILE = "manifest.json"
OBJECTS_DIR = "objects"


def default_cache_dir() -> Path:
    override = config.get("cache_dir")
    if override is not None:
        return Path(override)
    return Path(platformdirs.user_cache_dir("fishbaseball"))


class Cache:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root is not None else default_cache_dir()

    # ---- paths --------------------------------------------------------------------------

    def source_dir(self, source: str) -> Path:
        return self.root / source

    def version_dir(self, source: str, tag: str) -> Path:
        return self.source_dir(source) / tag

    def table_path(self, source: str, tag: str, table: str) -> Path:
        return self.version_dir(source, tag) / f"{table}.parquet"

    def object_path(self, source: str, sha256: str) -> Path:
        """Where a partition file lives, named by its own SHA-256: the same bytes are stored
        once however many releases' manifests reference them, and a file can only exist here
        after it passed verification (downloads are verified before they're moved in)."""
        return self.source_dir(source) / OBJECTS_DIR / f"{sha256}.parquet"

    def release_dirs(self, source: str) -> list[Path]:
        """Every cached release directory for `source` (the objects store is not one)."""
        source_dir = self.source_dir(source)
        if not source_dir.is_dir():
            return []
        return sorted(p for p in source_dir.iterdir() if p.is_dir() and p.name != OBJECTS_DIR)

    def manifest_path(self, source: str, tag: str) -> Path:
        return self.version_dir(source, tag) / MANIFEST_FILE

    def pointer_path(self, source: str) -> Path:
        return self.source_dir(source) / POINTER_FILE

    def _metadata_path(self) -> Path:
        return self.root / METADATA_FILE

    # ---- generic json read/write ---------------------------------------------------------

    def read_json(self, path: Path) -> dict[str, Any] | None:
        """None for a missing or unparsable file: a corrupt cache entry forces a fresh
        download rather than crashing the caller."""
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def write_json_atomic(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)

    # ---- metadata (locked read-modify-write) ---------------------------------------------

    def read_metadata(self) -> dict[str, dict[str, Any]]:
        return self.read_json(self._metadata_path()) or {}

    def get_metadata(self, source: str) -> dict[str, Any] | None:
        return self.read_metadata().get(source)

    def update_metadata(self, source: str, **fields: Any) -> None:
        """Merge `fields` into `metadata[source]`, holding a file lock across the whole
        read-modify-write so two processes updating different (or the same) sources don't
        clobber each other."""
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self._metadata_path().with_suffix(".json.lock")
        with FileLock(str(lock_path)):
            data = self.read_metadata()
            data[source] = {**data.get(source, {}), **fields}
            self.write_json_atomic(self._metadata_path(), data)

    def is_stale(self, source: str, *, ttl: float, now: datetime) -> bool:
        meta = self.get_metadata(source)
        if not meta or not meta.get("last_checked"):
            return True
        last_checked = datetime.fromisoformat(meta["last_checked"])
        if last_checked.tzinfo is None:
            last_checked = last_checked.replace(tzinfo=timezone.utc)
        return now >= last_checked + timedelta(seconds=ttl)

    # ---- purge / info ---------------------------------------------------------------------

    def purge(self, source: str | None = None, *, version: str | None = None) -> None:
        if source is None:
            shutil.rmtree(self.root, ignore_errors=True)
            return
        if version is not None:
            shutil.rmtree(self.version_dir(source, version), ignore_errors=True)
            self.remove_unreferenced_objects(source)
            return
        shutil.rmtree(self.source_dir(source), ignore_errors=True)
        lock_path = self._metadata_path().with_suffix(".json.lock")
        with FileLock(str(lock_path)):
            data = self.read_metadata()
            data.pop(source, None)
            self.write_json_atomic(self._metadata_path(), data)

    def remove_unreferenced_objects(self, source: str) -> None:
        """Delete stored partition files that no cached release's manifest references any
        more, e.g. after purging the only release that used them."""
        objects = self.source_dir(source) / OBJECTS_DIR
        if not objects.is_dir():
            return
        referenced = {
            partition["sha256"]
            for release in self.release_dirs(source)
            for entry in (
                (self.read_json(release / MANIFEST_FILE) or {}).get("tables") or {}
            ).values()
            for partition in (entry.get("partitions") or {}).values()
        }
        for path in objects.glob("*.parquet"):
            if path.stem not in referenced:
                path.unlink(missing_ok=True)

    def info(self) -> list[dict[str, Any]]:
        """One row per cached (source, release, table). `partitions` is how many of a
        partitioned table's partition files are cached (`None` for whole-file tables)."""
        rows: list[dict[str, Any]] = []
        if not self.root.is_dir():
            return rows
        for source_dir in sorted(p for p in self.root.iterdir() if p.is_dir()):
            for version_dir in self.release_dirs(source_dir.name):
                for table_file in sorted(version_dir.glob("*.parquet")):
                    rows.append(
                        {
                            "source": source_dir.name,
                            "version": version_dir.name,
                            "table": table_file.stem,
                            "bytes": table_file.stat().st_size,
                            "partitions": None,
                        }
                    )
                tables = (self.read_json(version_dir / MANIFEST_FILE) or {}).get("tables") or {}
                for table, entry in sorted(tables.items()):
                    if not entry.get("partitioned"):
                        continue
                    sizes = [
                        self.object_path(source_dir.name, p["sha256"]).stat().st_size
                        for p in entry["partitions"].values()
                        if self.object_path(source_dir.name, p["sha256"]).exists()
                    ]
                    if sizes:
                        rows.append(
                            {
                                "source": source_dir.name,
                                "version": version_dir.name,
                                "table": table,
                                "bytes": sum(sizes),
                                "partitions": len(sizes),
                            }
                        )
        return rows
