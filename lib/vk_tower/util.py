# Copyright 2025 Google
# SPDX-License-Identifier: MIT

import json
import os
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
