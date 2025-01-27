# Copyright 2025 Google
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
import json as std_json
from os import fspath, PathLike
from pathlib import Path
import sys

# external
import json5

@dataclass
class JsonFileError(RuntimeError):

    path: PathLike

    def __str__(self):
        path = fspath(self.path)
        return f"failed to load json file: {path!r}"

def _serialize_default(obj):
    """For param `builtins.json.dump(..., default)`."""

    if isinstance(obj, PathLike):
        return fspath(obj)
    elif isinstance(obj, set):
        return list(sorted(obj))
    else:
        # Mimic the error message of `json.dump`.
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

def pprint(obj, /, *, file=sys.stdout, format="json"):
    """Pretty-print JSON."""

    match format:
        case "json":
            dump = std_json.json.dump
        case "json5":
            dump = json5.dump
        case _:
            raise ValueError(f"invalid format: {format!r}")

    dump(obj, file, indent=4, default=_serialize_default)
    file.write("\n")

def load_path(path: PathLike):
    """Load a json file. Autodetct the json dialect."""

    path = Path(path)

    match path.suffix:
        case ".json":
            load = std_json.load
        case ".json5":
            load = json5.load
        case _:
            # Assume regular json
            load = std_json.load

    with path.open("r") as f:
        try:
            return load(f)
        except Exception as e:
            raise JsonFileError(path=path) from e
