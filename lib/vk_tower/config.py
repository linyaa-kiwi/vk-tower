# Copyright 2024 Google
# SPDX-License-Identifier: MIT

import os
from os import PathLike
from pathlib import Path
from typing import Iterator

from xdg_base_dirs import (
    xdg_data_home,
    xdg_data_dirs,
)

from .util import (
    parse_env_bool,
    parse_xdg_env_path_list,
)

class Config:
    """
    Config Settings.

    Environment Variables:
        - VK_TOWER_REGISTRY_PATH
        - VK_TOWER_REGISTRY_EXTRA_FILES
        - VK_TOWER_REGISTRY_IGNORE_XDG_PATHS
        - XDG_DATA_DIRS
        - XDG_DATA_HOME
    """

    xdg_data_dirs: [Path]
    xdg_data_home: Path
    registry_ignore_xdg_paths: bool
    registry_system_paths: [Path]
    registry_user_path: Path | None
    registry_extra_paths: [Path]
    registry_extra_files: [Path]

    def __init__(self):
        self.xdg_data_dirs = xdg_data_dirs()
        self.xdg_data_home = xdg_data_home()

        self.registry_ignore_xdg_paths = \
            parse_env_bool("VK_TOWER_REGISTRY_IGNORE_XDG_PATHS", False)

        if self.registry_ignore_xdg_paths:
            self.registry_system_paths = []
            self.registry_user_path = None
        else:
            self.registry_system_paths = [
                x / "vulkan/registry"
                for x in self.xdg_data_dirs
            ]
            self.registry_user_path = self.xdg_data_home / "vulkan/registry"

        self.registry_extra_paths = \
                    parse_xdg_env_path_list("VK_TOWER_REGISTRY_PATH")

    def iter_registry_paths(self) -> Iterator[Path]:
        """Iterate over top-level registry directories.

        Yield in order of descending priority.
        """
        for x in self.registry_extra_paths:
            yield x
        if self.registry_user_path is not None:
            yield self.registry_user_path
        for x in self.registry_system_paths:
            yield x

    def to_porcelain_json(self):
        def map_fspath(paths: [PathLike]) -> [str]:
            return list(os.fspath(x) for x in paths)

        return {
            "xdg_data_dirs": map_fspath(self.xdg_data_dirs),
            "xdg_data_home": os.fspath(self.xdg_data_home),
            "registry_ignore_xdg_paths": self.registry_ignore_xdg_paths,
            "registry_system_paths": map_fspath(self.registry_system_paths),
            "registry_user_path": os.fspath(self.registry_user_path),
            "registry_extra_paths": map_fspath(self.registry_extra_paths),
            "registry_paths": map_fspath(self.iter_registry_paths()),
        }
