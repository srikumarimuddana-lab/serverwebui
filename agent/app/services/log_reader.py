import os


class LogReader:
    def __init__(self, config):
        self.config = config

    def read_log(self, path: str, offset: int = 0, limit: int = 50) -> dict:
        resolved = os.path.realpath(path)
        if not self.config.is_path_allowed(resolved):
            raise PermissionError(f"Access denied: {path}")
        if not os.path.isfile(resolved):
            raise FileNotFoundError(f"Not a file: {path}")

        with open(resolved, "r", errors="replace") as f:
            all_lines = f.readlines()

        total = len(all_lines)
        selected = all_lines[offset:offset + limit]
        return {
            "path": resolved,
            "total_lines": total,
            "offset": offset,
            "limit": limit,
            "lines": [line.rstrip("\n") for line in selected],
        }
