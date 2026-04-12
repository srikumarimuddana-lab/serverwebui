import os
import shutil
from pathlib import Path


class FileManager:
    def __init__(self, config):
        self.config = config

    def _check_path(self, path: str) -> str:
        resolved = os.path.realpath(path)
        if not self.config.is_path_allowed(resolved):
            raise PermissionError(f"Access denied: {path}")
        return resolved

    def list_directory(self, path: str) -> dict:
        resolved = self._check_path(path)
        if not os.path.isdir(resolved):
            raise FileNotFoundError(f"Not a directory: {path}")
        entries = []
        for entry in os.scandir(resolved):
            stat = entry.stat(follow_symlinks=False)
            entries.append({
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
        entries.sort(key=lambda e: (e["type"] != "directory", e["name"].lower()))
        return {"type": "directory", "path": resolved, "entries": entries}

    def read_file(self, path: str) -> str:
        resolved = self._check_path(path)
        if not os.path.isfile(resolved):
            raise FileNotFoundError(f"Not a file: {path}")
        return resolved

    def write_file(self, path: str, content: bytes) -> str:
        resolved = self._check_path(path)
        parent = os.path.dirname(resolved)
        os.makedirs(parent, exist_ok=True)
        with open(resolved, "wb") as f:
            f.write(content)
        return resolved

    def delete(self, path: str) -> None:
        resolved = self._check_path(path)
        if os.path.isdir(resolved):
            shutil.rmtree(resolved)
        elif os.path.isfile(resolved):
            os.remove(resolved)
        else:
            raise FileNotFoundError(f"Not found: {path}")

    def rename(self, old_path: str, new_path: str) -> str:
        resolved_old = self._check_path(old_path)
        resolved_new = self._check_path(new_path)
        os.rename(resolved_old, resolved_new)
        return resolved_new
