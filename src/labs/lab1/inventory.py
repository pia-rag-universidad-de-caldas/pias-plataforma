from pathlib import Path
import json
from typing import Any

def find_json_files(root: str | Path) -> list[Path]:
    directory = Path(root)

    if not directory.exists():
        raise FileNotFoundError(
            f"No existe la carpeta indicada: {directory}"
        )

    if not directory.is_dir():
        raise NotADirectoryError(
            f"La ruta no es una carpeta: {directory}"
        )

    excluded_dirs = {".venv", ".git", "__pycache__"}

    return sorted(
        path
        for path in directory.rglob("*.json")
        if path.is_file()
        and not excluded_dirs.intersection(path.parts)
    )

def load_json(path: str | Path) -> Any:
    file_path = Path(path)

    with open(file_path, "r", encoding="utf-8-sig")as file:
        return json.load(file)

def inspect_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)

    result: dict[str, Any] = {
        "path": str(file_path),
        "filename": file_path.name,
        "size_bytes": file_path.stat().st_size,
        "valid_json": False,
        "error": None,
    }

    try:
        data = load_json(file_path)
        result["valid_json"] = True
        result["root_type"] = type(data).__name__
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        result["error"] = str(error)
    except OSError as error:
        result["error"] = str(error)

    return result


def inventory(root: str | Path) -> list[dict[str, Any]]:
    return [
        inspect_json(path)
        for path in find_json_files(root)
    ]