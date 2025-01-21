# Copyright 2025 Google
# SPDX-License-Identifier: MIT

from dataclasses import dataclass, field, KW_ONLY
import enum
from itertools import chain
import os
from os import PathLike
from pathlib import Path
import re
from typing import Iterator, Optional

from .config import Config
from .util import dig, json_load_path

CapName = str
ProfileName = str

class RegistryFileNotFoundError(RuntimeError):

    name: str

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"registry file not found: {self.name!r}"

class ProfileNotFoundError(RuntimeError):

    profile: str

    def __init__(self, profile: str):
        self.profile = profile

    def __str__(self):
        return f"profile not found: {self.profile!r}"

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

class ProfilesFile:
    """The data contained in a profiles file, such as `VP_KHR_roadmap.json`."""

    __data: dict | None
    reg_file: RegistryFile

    @staticmethod
    def from_path(path: PathLike) -> "ProfilesFile":
        type = RegistryFiletype.profiles
        reg_file = RegistryFile.from_path(type, path)
        return ProfilesFile(reg_file)

    def __init__(self, reg_file: RegistryFile):
        self.reg_file = reg_file
        self.__data = None

    @property
    def data(self) -> dict:
        if self.__data is None:
            self.__data = json_load_path(self.reg_file.path)

            if not isinstance(self.__data, dict):
                path = os.fspath(self.reg_file.path)
                raise ProfileValidationError(f"profiles file does not contain "
                                             f"a json dict: {path!r}")

        return self.__data

    def get_profile_obj(self, name: str, /, *,
                        missing_ok=False) -> dict | None:
        p = dig(self.data, "profiles", name)
        if p is not None:
            return p

        if missing_ok:
            return None

        raise ProfileNotFoundError(name)

    def iter_profile_names(self) -> Iterator[str]:
        table = self.data.get("profiles")
        if table is None:
            return
        for name in table:
            yield name

    def iter_profile_objs(self) -> Iterator[dict]:
        table = self.data.get("profiles")
        if table is None:
            return
        for obj in table.values():
            yield obj

    def remove_optionals(self) -> None:
        """Remove member `optionals` from all profiles."""
        for profile_obj in self.iter_profile_objs():
            profile_obj.pop("optionals", None)

    def get_profile_internal_deps(self, profile_name: str, /) -> "ProfileInternalDeps":
        """See `ProfileInternalDeps`."""

        main_profile_name = profile_name
        del profile_name

        deps = ProfileInternalDeps()

        def collect_profiles():
            visited = set()
            stack: [str] = [main_profile_name]

            while stack:
                profile_name: str = stack.pop()
                assert isinstance(profile_name, str)

                assert profile_name not in visited
                visited.add(profile_name)

                profile_obj = self.get_profile_obj(profile_name, missing_ok=True)
                if profile_obj is None:
                    deps.external_profile_names.add(profile_name)
                    continue

                deps.local_profile_names.add(profile_name)

                for dep_name in dig(profile_obj, "profiles", default=[]):
                    if dep_name not in visited:
                        stack.append(dep_name)

        collect_profiles()

        def collect_caps():
            for profile_name in deps.local_profile_names:
                profile_obj = self.get_profile_obj(profile_name)

                stack = []
                stack += profile_obj.get("capabilities", [])
                stack += profile_obj.get("optionals", [])

                while stack:
                    cap = stack.pop()

                    if isinstance(cap, str):
                        if cap not in deps.local_cap_names:
                            deps.local_cap_names.add(cap)
                    elif isinstance(cap, list):
                        for sub_cap in cap:
                            stack.append(sub_cap)
                    else:
                        path = os.fspath(self.file.reg_file.path)
                        msg = f"invalid data in profiles file: {path!r}"
                        raise ProfileValidationError(msg)

        collect_caps()

        return deps

    def trim_to_profile(self, name: str) -> None:
        """
        Discard profiles and capability sets not referenced by the profile.

        For the requested profile name, collect the names of all profiles and
        capability sets that the profile recursively references, local to this
        file.  Then delete all other profiles and capability sets.
        """
        deps = self.get_profile_internal_deps(name)

        profiles = self.data.get("profiles")
        good_names = deps.local_profile_names | deps.external_profile_names
        bad_names = set(profiles.keys()) - good_names
        for name in bad_names:
            profiles.pop(name)

        caps = self.data.get("capabilities")
        good_names = deps.local_cap_names
        bad_names = set(caps.keys()) - good_names
        for name in bad_names:
            caps.pop(name)

class Registry:

    config: Config

    __vkxml_files: dict[str, RegistryFile]
    """Key is `RegistryFile.name`."""

    __profiles_files: dict[str, ProfilesFile]
    """Key is `RegistryFile.name`."""

    __profiles_schema_files: dict[str, RegistryFile]
    """Key is `RegistryFile.name`."""

    __loaded_profiles_files: set[str]
    """Keys are `RegistryFile.name`."""

    __profiles: dict[str, "Profile"]
    """Key is `Profile.name`."""

    def __init__(self, config: Config):
        self.config = config
        assert all(map(Path.is_absolute, self.config.iter_registry_paths()))

        self.__vkxml_files = {}
        self.__profiles_files = {}
        self.__profiles_schema_files = {}

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
        self.__files[type].setdefault(reg_file.name, reg_file)

    def __collect_vkxml_files(self) -> None:
        for path in self.__iter_glob_files("*.xml"):
            type = RegistryFiletype.vkxml
            reg_file = RegistryFile.from_path(type, path)
            self.__vkxml_files.setdefault(reg_file.name, reg_file)

    def __collect_profiles_files(self) -> None:
        # Descend into subdirs.
        for path in chain(self.__iter_glob_files("profiles/**/*.json"),
                          self.__iter_glob_files("profiles/**/*.json5")):
            if not re.match(r"^(?:VP|vp)_.+\.(?:json|json5)$", path.name):
                continue
            file = ProfilesFile.from_path(path)
            self.__profiles_files.setdefault(file.reg_file.name, file)

    def __collect_profiles_schema_files(self) -> None:
        # Do not descend into subdirs.
        for path in chain(self.__iter_glob_files("schemas/profiles-*.json"),
                          self.__iter_glob_files("schemas/profiles-*.json5")):
            type = RegistryFiletype.profiles_schema
            reg_file = RegistryFile.from_path(type, path)
            self.__profiles_schema_files.setdefault(reg_file.name, reg_file)

    def iter_files(self) -> Iterator[RegistryFile]:
        for x in chain(self.__vkxml_files.values(),
                       self.__profiles_files.values(),
                       self.__profiles_schema_files.values()):
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

    def get_vk_xml_file(self, *, missing_ok=False) -> Optional[RegistryFile]:
        name = "vk.xml"

        reg_file = self.__vkxml_files.get(name)
        if reg_file.name is not None:
            return reg_file

        if missing_ok:
            return None

        raise RegistryFileNotFoundError(name)

    def __load_profiles_file(self, file: ProfilesFile) -> Iterator["Profile"]:
        """
        Fully load a profiles file and yield its profiles.

        Skip if a profiles file with the same name has already been loaded.
        """

        if file.reg_file.name in self.__loaded_profiles_files:
            return

        profile_names = list(file.iter_profile_names())

        # Check if the file redefines any profile previously defined in the
        # registry. To improve data consistency under exceptions, do the check
        # before registering new profiles.
        for name in profile_names:
            profile = self.__profiles.get(name)
            if profile is not None:
                raise ProfileRedefinitionError(
                        orig_profile = profile,
                        bad_reg_file = reg_file)

        profiles = {
            name: Profile(name=name, file=file)
            for name in profile_names
        }

        self.__loaded_profiles_files.add(file.reg_file.name)
        self.__profiles.update(profiles)

        # Do not yield any new profiles until all of them have been added to the
        # registry. Otherwise, the caller may stop the iterator before it
        # completes, which causes the file to be marked as loaded before all of
        # its profiles have been loaded.
        for x in profiles.values():
            yield x

    def __lazy_load_profiles(self) -> Iterator["Profile"]:
        """
        Lazily load more profiles.

        Yield each profile as it is loaded.  Previously loaded profiles are
        skipped.
        """
        for file in self.__profiles_files.values():
            for profile in self.__load_profiles_file(file):
                # Reduce latency by yielding each profile as it is loaded.
                yield profile

    def iter_profiles(self) -> Iterator["Profile"]:
        # Reduce latency by first yielding previously loaded profiles.
        for x in self.__profiles.values():
            yield x

        # Reduce latency by yielding each profile as it is loaded.
        for x in self.__lazy_load_profiles():
            yield x

    def get_profile(self, name: str, /, *,
                    missing_ok=False) -> Optional["Profile"]:
        p = self.__profiles.get(name)
        if p is not None:
            return p

        for p in self.__lazy_load_profiles():
            if p.name == name:
                return p

        if missing_ok:
            return None

        raise ProfileNotFoundError(name)

    def get_profile_recursive_deps(self, name: str) -> "ProfileGlobalDeps":
        main_profile = self.get_profile(name, missing_ok=False)
        gdeps = ProfileGlobalDeps()

        stack: [Profile] = [main_profile]
        visited: set[ProfileName] = set()

        while stack:
            profile = stack.pop()
            visited.add(profile.name)

            ideps = profile.file.get_profile_internal_deps(profile.name)

            # Ignore `ideps.local_profiles_names` because
            # `ideps.local_cap_names` already contains all the needed caps.

            for name in ideps.local_cap_names:
                pc = ProfileCapability(profile, name)
                gdeps.caps.setdefault(pc.key, pc)

            for name in ideps.external_profile_names:
                if name in visited:
                    continue

                child = self.get_profile(name)
                if child is None:
                    gdeps.undefined_profiles.add(name)
                    continue

                stack.append(child)

        return gdeps

@dataclass
class ProfileInternalDeps:
    """
    Profile dependencies that are internal to a profiles file.

    When building this object, all dependencies are recursively expanded.

    For example, consider the following profiles file.
    ```
    {
        profiles: {
            VP_apple: {
                ...,
                profiles: [
                    "VP_banana",
                ],
                capabilities: [
                    "cap_00",
                    ["cap_01", "cap_02"],
                ],
            },
            VP_banana: {
                profiles: [
                    "VP_canteloupe",
                    "VP_zebra", // defined externally
                ],
                capabilities: [
                    "cap_03",
                    "cap_04",
                ],
                optionals: [
                    "cap_05", // optionals are included too
                ],
            }
            VP_canteloupe: {
                profiles: [],
                capabilities: [
                    "cap_06",
                ],
            },
            VP_durian: { // not in VP_apple's recursive dependencies
                profiles: [],
                capabilities: [
                    "cap_07",
                ],
            },
        },
    }
    ```

    Then the internal dependencies of VP_apple are:
    ```
    local_profiles_names: ["VP_banana", "VP_canteloupe"]
    local_cap_names: ["cap_00", "cap_01", "cap_02", "cap_03", "cap_04",
                      "cap_05", "cap_06"]
    external_profile_names: ["VP_zebra"]
    ```
    """

    _: KW_ONLY

    local_profile_names:        set[str] = field(default_factory=set)
    local_cap_names:            set[str] = field(default_factory=set)
    external_profile_names:     set[str] = field(default_factory=set)

@dataclass
class Profile:

    _: KW_ONLY
    name: str
    file: ProfilesFile

@dataclass
class ProfileCapability:

    Key = (Profile, CapName)

    profile: Profile
    cap: CapName

    @property
    def key(self):
        return (self.profile.name, self.cap)

@dataclass
class ProfileGlobalDeps:
    """
    Profile dependencies, recursively expanded using the full registry.

    When building this object, all dependencies are recursively expanded.
    The object contains only the leaf nodes from the expansion.
    As a consequence, the only profile names remaining after expansion are those
    profiles not defined in the registry.
    """

    caps: dict[ProfileCapability.Key, ProfileCapability]
    undefined_profiles: set[ProfileName]

    def __init__(self):
        self.caps = {}
        self.undefined_profiles = set()
