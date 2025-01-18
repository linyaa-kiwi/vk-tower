# Copyright 2025 Google
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
import json
import os
from os import fspath, PathLike
from pathlib import Path
import sys

import json5

@dataclass
class JsonFileError(RuntimeError):

    path: PathLike
    orig_error: Exception

    def __str__(self):
        path = os.fspath(self.path)
        return f"failed to load json file: {path!r}"


def _json_default(x):
    if isinstance(x, os.PathLike):
        return os.fspath(x)
    else:
        # Mimic the error message of `json.dump`.
        raise TypeError(f"Object of type {type(x)} is not JSON serializable")

def json_pp(obj, /, *, file=sys.stdout, format="json"):
    """Pretty-print JSON."""
    match format:
        case "json":
            dump = json.dump
        case "json5":
            dump = json5.dump
        case _:
            raise ValueError(f"invalid format: {format!r}")

    dump(obj, file, indent=4, default=_json_default)
    file.write("\n")

def json_load_path(path: PathLike):
    """Load a json file. Autodetct the json dialect."""

    path = Path(path)

    match path.suffix:
        case ".json":
            load = json.load
        case ".json5":
            load = json5.load
        case _:
            # Assume regular json
            load = json.load

    with path.open("r") as f:
        try:
            return load(f)
        except Exception as e:
            raise JsonFileError(orig_error=e, path=path)

def parse_env_bool(name: str, default: bool) -> bool:
    env = os.environ.get(name, "").lower()
    match env:
        case "true" | "1":
            return True
        case "false" | "0":
            return False
        case _:
            return default

def parse_xdg_env_path_list(name: str) -> [Path]:
    """Parse the environment variable `name` as a list of paths, following the
    parsing rules in the XDG Base Directory specification.

    Relative paths and empty paths are ignored. If the environment variable is
    unset, return the empty list.
    """
    paths = []

    for path_str in os.environ.get(name, "").split(os.pathsep):
        if path_str == "":
            continue

        path = Path(path_str)
        if not path.is_absolute():
            continue

        paths.append(path)

    return paths
