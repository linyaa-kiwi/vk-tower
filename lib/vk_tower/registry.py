# Copyright 2025 Google
# SPDX-License-Identifier: MIT

from dataclasses import dataclass, KW_ONLY
import enum
from itertools import chain
import os
from os import PathLike
from pathlib import Path
import re
from typing import Iterator, Optional

from .config import Config
from .util import json_load_path

class ProfileRedefinitionError(RuntimeError):

    orig_profile: "Profile"
    bad_reg_file: "RegistryFile"

class RegistryFiletype(enum.IntEnum):
    # IntEnum provides a total order.
    vkxml = enum.auto()
    profiles = enum.auto()
    profiles_schema = enum.auto()

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
            case (RegistryFiletype.profiles |
                  RegistryFiletype.profiles_schema):
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
    """Middle key is `RegistryFile.name`."""

    __loaded_profiles_files: set[str]
    """Keys are `RegistryFile.name`."""

    __profiles: dict[str, "Profile"]
    """Key is `Profile.name`."""

    def __init__(self, config: Config):
        self.config = config
        assert all(map(Path.is_absolute, self.config.iter_registry_paths()))

        self.__files = {
            RegistryFiletype.vkxml: {},
            RegistryFiletype.profiles: {},
            RegistryFiletype.profiles_schema: {},
        }

        # To ensure that register queries have consistent results over the
        # registry's lifetime, for a given filetype (profile, schema, etc)
        # we collect its files exactly once.
        #
        # TODO: Lazily collect files.
        self.__collect_vkxml_files()
        self.__collect_profiles_files()
        self.__collect_profiles_schema_files()

        self.__profiles = {}
        self.__loaded_profiles_files = set()

    def __add_file(self, type: RegistryFiletype, path: PathLike) -> None:
        path = Path(path)
        reg_file = RegistryFile.from_path(type, path)
        self.__files[type].setdefault(reg_file.name, reg_file)

    def __collect_vkxml_files(self) -> None:
        for path in self.__iter_glob_files("*.xml"):
            self.__add_file(RegistryFiletype.vkxml, path)

    def __collect_profiles_files(self) -> None:
        # Descend into subdirs.
        for path in chain(self.__iter_glob_files("profiles/**/*.json"),
                          self.__iter_glob_files("profiles/**/*.json5")):
            if re.match(r"^(?:VP|vp)_.+\.(?:json|json5)$", path.name):
                self.__add_file(RegistryFiletype.profiles, path)

    def __collect_profiles_schema_files(self) -> None:
        # Do not descend into subdirs.
        for path in chain(self.__iter_glob_files("schemas/profiles-*.json"),
                          self.__iter_glob_files("schemas/profiles-*.json5")):
            self.__add_file(RegistryFiletype.profiles_schema, path)

    def iter_files(self) -> Iterator[RegistryFile]:
        for type in RegistryFiletype:
            for reg_file in self.__files[type].values():
                yield reg_file

    def iter_vkxml_files(self) -> Iterator[RegistryFile]:
        for x in self.__files[RegistryFiletype.vkxml].values():
            yield x

    def iter_profiles_files(self) -> Iterator[RegistryFile]:
        for x in self.__files[RegistryFiletype.profiles].values():
            yield x

    def iter_profiles_schema_files(self) -> Iterator[RegistryFile]:
        for x in self.__files[RegistryFiletype.profiles_schema].values():
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

    def __load_profiles_file(self, reg_file: RegistryFile) -> Iterator["Profile"]:
        """
        Fully load a profiles file and yield its profiles.

        Skip if a profiles file with the same name has already been loaded.
        """

        if reg_file.name in self.__loaded_profiles_files:
            return

        data = json_load_path(reg_file.path)
        profile_names = data["profiles"]keys()

        # Check if the file redefines any profile previously defined in the
        # registry. To improve data consistency under exceptions, do the check
        # before loading new profiles.
        for name in profile_names:
            profile = self.__profiles.get(name)
            if profile is not None:
                raise ProfileRedefinitionError(
                        orig_profile = profile,
                        bad_reg_file = reg_file)

        profiles = {
            name: Profile(name=name, data=data, reg_file=reg_file)
            for name in profile_names
        }

        self.__loaded_profiles_files.add(reg_file.name)
        self.__profiles.update(profiles)

        # Do not yield any new profiles until all of them have been added to the
        # registry. Otherwise, the caller may stop the iterator before it
        # completes, which causes the file to be marked as loaded before all of
        # its profiles have been loaded.
        for x in profiles.values():
            yield x

    def __load_profiles(self) -> Iterator["Profile"]:
        """Yield any newly loaded profiles."""
        for reg_file in self.iter_profiles_files():
            for profile in self.__load_profiles_file(reg_file):
                # Reduce latency by yielding each profile as it is loaded.
                yield profile

    def iter_profiles(self) -> Iterator["Profile"]:
        # Reduce latency by first yielding previously loaded profiles.
        for x in self.__profiles.values():
            yield x

        # Reduce latency by yielding each profile as it is loaded.
        for x in self.__load_profiles():
            yield x

    def get_profile(self, name: str, /) -> Optional["Profile"]:
        p = self.__profiles.get(name)
        if p is not None:
            return p

        for p in self.__load_profiles():
            if p.name == name:
                return p

        return None

@dataclass
class Profile:

    _: KW_ONLY
    name: str

    data: dict
    """
    The data that is usually contained in a profile file and conforms to
    a profile schema.
    """

    reg_file: RegistryFile | None
