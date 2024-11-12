# Copyright 2024 Google
# SPDX-License-Identifier: MIT

import click

from .config import Config
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

def main():
    cmd_main()

if __name__ == "__main__":
    main()
