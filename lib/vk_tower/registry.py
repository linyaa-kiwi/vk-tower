# Copyright 2025 Google
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
import enum
import os
from os import PathLike
from pathlib import Path
from typing import Iterator

from .config import Config

class RegistryFiletype(enum.IntEnum):
    # IntEnum provides a total order.
    vkxml = enum.auto()
    profile = enum.auto()
    profile_schema = enum.auto()

    def to_porcelain_json(self):
        return self._name_

@dataclass(frozen=True, order=True)
class RegistryFile:
    """
    A registry file.

    The tuple `(type, name)` is a unique key in the registry.
    """

    type: RegistryFiletype
    name: str
    path: Path

    def __post_init__(self):
        if not self.path.is_absolute():
            raise ValueError(f"path is not absolute: {path!r}")
        if not self.path.is_file():
            raise ValueError(f"path is not a file: {path!r}")

    @staticmethod
    def from_path(type: RegistryFiletype, path: PathLike, /) -> "RegistryFile":
        path = Path(path)

        match type:
            case RegistryFiletype.vkxml:
                if path.suffix != ".xml":
                    raise ValueError(f"registry file has invalid suffix: {path!r}")
                name = path.name
            case (RegistryFiletype.profile |
                  RegistryFiletype.profile_schema):
                if path.suffix not in (".json", ".json5"):
                    raise ValueError(f"registry file has invalid suffix: {path!r}")
                name = path.stem
            case _:
                assert False

        return RegistryFile(type, name, path)

    def to_porcelain_json(self):
        return {
            "type": self.type.to_porcelain_json(),
            "name": self.name,
            "path": os.fspath(self.path),
        }

class Registry:

    config: Config
    __files: dict[RegistryFiletype, dict[str, RegistryFile]]

    def __init__(self, config: Config):
        self.config = config
        assert all(map(Path.is_absolute, self.config.iter_registry_paths()))

        self.__files = {
            RegistryFiletype.vkxml: {},
            RegistryFiletype.profile: {},
            RegistryFiletype.profile_schema: {},
        }

        # To ensure that register queries have consistent results over the
        # registry's lifetime, for a given filetype (profile, schema, etc)
        # we collect its files exactly once.
        #
        # TODO: Lazily collect files.
        self.__collect_vkxml_files()
        self.__collect_profile_files()
        self.__collect_profile_schema_files()

    def __add_file(self, type: RegistryFiletype, path: PathLike) -> None:
        path = Path(path)
        reg_file = RegistryFile.from_path(type, path)
        self.__files[type].setdefault(reg_file.name, reg_file)

    def add_vkxml_file(self, path: PathLike, /) -> None:
        self.__add_file(RegistryFiletype.vkxml, path)

    def add_profile_file(self, path: PathLike, /) -> None:
        self.__add_file(RegistryFiletype.profile, path)

    def add_profile_schema_file(self, path: PathLike, /) -> None:
        self.__add_file(RegistryFiletype.profile_schema, path)

    def __collect_vkxml_files(self) -> None:
        for path in self.__iter_glob_files("vk.xml"):
            self.add_vkxml_file(path)

    def __collect_profile_files(self) -> None:
        # Descend into subdirs.
        for path in self.__iter_glob_files("profiles/**/*.json"):
            self.add_profile_file(path)

    def __collect_profile_schema_files(self) -> None:
        # Do not descend into subdirs.
        for path in self.__iter_glob_files("schema/profiles-*.json"):
            self.add_profile_schema_file(path)

    def iter_files(self) -> Iterator[RegistryFile]:
        for type in RegistryFiletype:
            for reg_file in self.__files[type].values():
                yield reg_file

    def iter_vkxml_files(self) -> Iterator[RegistryFile]:
        for x in self.__files[RegistryFiletype.vkxml].values():
            yield x

    def iter_profile_files(self) -> Iterator[RegistryFile]:
        for x in self.__files[RegistryFiletype.profile].values():
            yield x

    def iter_profile_schema_files(self) -> Iterator[RegistryFile]:
        for x in self.__files[RegistryFiletype.profile_schema].values():
            yield x

    def __iter_glob_files(self, glob: str) -> Iterator[Path]:
        """Iterate over registry files that match a glob pattern.

        For each registry root, the glob pattern "{root}/{glob}" is searched.
        """
        assert not os.path.isabs(glob)
        for reg_root in self.config.iter_registry_paths():
            assert reg_root.is_absolute()
            for abs_path in reg_root.glob(glob):
                if abs_path.is_file():
                    yield abs_path
