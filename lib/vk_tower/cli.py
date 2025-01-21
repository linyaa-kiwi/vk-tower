# Copyright 2024 Google
# SPDX-License-Identifier: MIT

import os
import sys

import click

from .config import Config
from .registry import Registry
from .util import eprint, json_pp
from .registry_xml import RegistryXML

@click.group(
    name = "vk-tower",
    context_settings = {
        "help_option_names": ["-h", "--help"],
    },
)
def cmd_main():
    pass

@cmd_main.command(
    name = "config",
    short_help = "Show config settings",
)
@click.option("-F", "--format",
    type = click.Choice(["json", "json5"]),
    default = "json",
    help = "Choose output format. Default is `json`.",
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
@click.option("-F", "--format",
    default = "name",
    type = click.Choice(["json", "json5", "name", "abspath"]),
    help = """
        Choose output format. Default is `name`.
        Format `name` writes the name of the file, one per line.
        For consistency, for "profiles files" and "profiles schemas", the
        file suffix is stripped from the name.
        For example, `VP_foo.json` and `VP_foo.json5` both have
        the same name, `VP_foo`.
        Format `abspath` writes the absolute path to the file, one per line.
    """,
)
def cmd_ls_registry_files(format):
    out = sys.stdout
    config = Config()
    reg = Registry(config)
    reg_files = [
        x.to_porcelain_json()
        for x in list(sorted(reg.iter_files()))
    ]

    match format:
        case "name":
            ors = "\n"
            for f in reg_files:
                name = f["name"]
                out.write(f"{name}{ors}")
        case "abspath":
            ors = "\n"
            for f in reg_files:
                path = f["path"]
                out.write(f"{path}{ors}")
        case "json" | "json5":
            json_pp(reg_files, format=format)
        case _:
            assert False

@cmd_main.command(
    name = "ls-profiles",
    short_help = "List all profile names.",
)
@click.option("-F", "--format",
    default = "name",
    type = click.Choice(["json", "json5", "name", "name-origin"]),
    help = """
        Choose output format. Default is `name`.
        Format `name` writes the name of each profile, one per line.
        Format `name-origin` is similar; it also writes the profile's origin as
        an absolute path.
    """,
)
def cmd_ls_profiles(format):
    out = sys.stdout
    config = Config()
    reg = Registry(config)

    match format:
        case "name":
            ors = "\n"
            for profile in reg.iter_profiles():
                out.write(f"{profile.name}{ors}")
        case "name-origin" | "name-origin0":
            ofs = ":"
            ors = "\n"
            for profile in reg.iter_profiles():
                # Currently all profiles are loaded from files.
                assert profile.reg_file is not None
                origin = os.fspath(profile.reg_file.path)
                name = profile.name
                out.write(f"{name}{ofs}{origin}{ors}")

        case "json" | "json5":
            profiles = []

            for profile in reg.iter_profiles():
                # Currently all profiles are loaded from files.
                assert profile.reg_file is not None

                profiles.append({
                    "name": profile.name,
                    "origin": {
                        "file": profile.reg_file.path,
                    },
                })

            json_pp(profiles, format=format)

        case _:
            assert False

@cmd_main.command(
    name = "print-profile",
    short_help = "Print a profile",
    help = """
        Print a profile.

        If no transformation is given, then print the full json object inside
        the profiles file that defines the requested profile. For example, if
        profile `VP_KHR_roadmap_2024` is requested, then print the full json
        object contained in `VP_KHR_roadmap.json`, which contains other profiles
        too.

        Transformations are applied in the order they are documented, not the
        order given on the cmdline.

        \b
        Transformations
            no-optionals
                For each profile object in the profiles file,
                remove the "optionals" member.
            trim:
                Collect the names of all profiles and capability sets that the
                profile recursively references, local to this file.  Then delete
                all other profiles and capability sets.
            normalize-vk-tokens
                If a token in the Vulkan API has been deprecated in favor of
                a new token, then replace the old with the new.
    """,
)
@click.argument("name", required = True)
@click.option("-F", "--format",
    type = click.Choice(["json", "json5"]),
    default = "json",
    help = "Choose the output format. Default is `json`.",
)
@click.option("-X", "--transform", "transforms",
    type = click.Choice(["no-optionals", "trim", "normalize-vk-tokens"]),
    multiple = True,
    help = """
        Apply transformation to the profiles file.
        Option can be given multiple times.
    """,
)
def cmd_print_profile(name, format, transforms):
    out = sys.stdout
    config = Config()
    reg = Registry(config)

    profile = reg.get_profile(name, missing_ok=True)
    if profile is None:
        eprint(f"profile not found: {name!r}")
        sys.exit(1)

    if "no-optionals" in transforms:
        profile.file.remove_optionals()
    if "trim" in transforms:
        profile.file.trim_to_profile(profile.name)
    if "normalize-vk-tokens" in transforms:
        profile.file.normalize_vk_names(reg.get_xml())

    json_pp(profile.file.data, format=format)

@cmd_main.command(
    name = "debug-dump-parsed-xml",
    hidden = True,
    help = "Dump all parsed XML as JSON.",
)
def cmd_debug_dump_parsed_xml():
    out = sys.stdout
    config = Config()
    reg = Registry(config)
    json_pp(reg.get_xml().to_json_obj())

def main():
    cmd_main()

if __name__ == "__main__":
    main()
