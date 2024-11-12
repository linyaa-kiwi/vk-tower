# Copyright 2025 Google
# SPDX-License-Identifier: MIT

import json
import os
from pathlib import Path
import sys

import json5

def _json_default(x):
    if isinstance(x, os.PathLike):
        return os.fspath(x)
    else:
        # Mimic the error message of `json.dump`.
        raise TypeError(f"Object of type {type(x)} is not JSON serializable")

def json_pp(obj, file=sys.stdout, /, *, format="json"):
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
