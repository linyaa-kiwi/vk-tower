# Copyright 2025 Google
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
import json
import logging
import os
from os import fspath, PathLike
from pathlib import Path
import sys

import json5

def get_log() -> logging.Logger:
    return logging.getLogger(name="vk-tower")

__debug_mode = None

def in_debug_mode() -> bool:
    global __debug_mode
    if __debug_mode is None:
        __debug_mode = parse_env_bool("VK_TOWER_DEBUG", False)
    return __debug_mode

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
    elif isinstance(x, set):
        return list(sorted(x))
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

def eprint(*args, **kwargs):
    file = kwargs.pop("file", sys.stderr)
    print(*args, file=file, **kwargs)

def dig(obj, *keys, default=None):
    """
    Dig into object.

    Iteratively dig into object by calling `__getitem__(key)`.
    If any step returns None, or if any key is not found, then return `default`.

    Like Ruby's `dig` method.
    """

    for k in keys:
        if obj is None:
            return None

        try:
            obj = obj[k]
        except LookupError:
            return default

    return obj
