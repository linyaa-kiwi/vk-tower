# Copyright 2024 Google
# SPDX-License-Identifier: MIT

import os
import sys

import click

from .config import Config
from .registry import Registry
from .util import json_pp

@click.group("vk-tower")
def cmd_main():
    pass

@cmd_main.command(
    name = "config",
    short_help = "Show config settings",
)
@click.option("-F", "--format",
    type = click.Choice(["json", "json5"]),
    default = "json",
    help = "Choose output format. Default is 'json'.",
)
def cmd_config(format):
    """Print the config settings as JSON.

    If a config value is a list, then it is sorted in descending priority.
    """
    config = Config()
    json_pp(config.to_porcelain_json(), format=format)

@cmd_main.command(
    name = "ls-registry-files",
    short_help = "List all registry files.",
    help = """
        List all registy files.

        If multiple instances of a filepath exists, where each filepath is
        considered relative to its containing registry root, then only the
        highest-priority instance is listed.
        """,
)
@click.option("-P", "--paths", "want_paths",
    flag_value = True,
    help = "Print filepaths if `--format=lines`. No change if `--format=json`.",
)
@click.option("-F", "--format",
    type = click.Choice(["lines", "lines0", "json", "json5"]),
    default = "lines",
    help = """Choose the output format. `lines` prints one item per line.
        `lines0` is the same, but the lines are null-terminated.""",
)
def cmd_ls_registry_files(format, want_paths):
    out = sys.stdout
    config = Config()
    reg = Registry(config)
    reg_files = [
        x.to_porcelain_json()
        for x in list(sorted(reg.iter_files()))
    ]

    match format:
        case "lines" | "lines0":
            sep = get_format_separator(format)
            for f in reg_files:
                out.write(f"{f['type']}/{f['name']}")
                if want_paths:
                    out.write(f":{f['path']}")
                out.write(sep)
        case "json" | "json5":
            json_pp(reg_files, format=format)
        case _:
            assert False

def get_format_separator(format: str) -> str:
    match format:
        case "lines":
            return "\n"
        case "lines0":
            return "\0"
        case _:
            raise ValueError(f"invalid format: {format!r}")

def main():
    cmd_main()

if __name__ == "__main__":
    main()
