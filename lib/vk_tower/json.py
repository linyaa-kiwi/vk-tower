# Copyright 2025 Google
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
import json as std_json
from os import fspath, PathLike
from pathlib import Path
from typing import Any
import sys

# external
import json5

Scalar = None | int | float | str
Value = dict[str, 'Value'] | list['Value'] | Scalar

def is_scalar(obj: Any) -> bool:
    """Is Python object a json scalar value?"""
    return isinstance(obj, Scalar)

def is_value_shallow(obj: Any) -> bool:
    """
    Is Python object a json value?

    This is a shallow test. If the Python object is a collection, it does not test its members.
    """
    # `isinstance` does not support parameterized generic types.
    return isinstance(obj, (dict, list, Scalar))

def is_value_deep(obj: Any) -> bool:
    """
    Is Python object a json value?

    This is a deep test. If the Python object is a collection, it recursively tests its members.
    """
    if isinstance(obj, dict):
        return all(isinstance(k, str) and is_value_deep(v)
                   for k, v in obj.items())
    elif isinstance(obj, list):
        return all(is_value_deep(x) for x in obj)
    else:
        return is_scalar(obj)

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
