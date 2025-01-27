# Copyright 2025 Google
# SPDX-License-Identifier: MIT

from copy import copy
from dataclasses import dataclass, KW_ONLY
import enum
from io import StringIO
from numbers import Number
from os import PathLike
import re
from typing import Any, Optional
import xml.etree.ElementTree as ET

from .util import get_log, in_debug_mode

_log = get_log()
debug = in_debug_mode()

StructName = str
MemberName = str

def vendor_get_sort_score(name: str):
    if not name:
        raise ValueError("empty vendor name")

    match name:
        case "KHR":
            return 0
        case "KHRX":
            return 1
        case "EXT":
            return 2
        case "EXTX":
            return 3
        case _:
            return 4

def extension_sort_key(name: str):
    """Key for sorting extension names."""
    m = re.match(r"^VK_([^_]+)_", name)
    assert m is not None
    return (vendor_get_sort_score(m[1]), name)

def struct_sort_key(name: str):
    m = re.match(r"^Vk\w+([A-Z]{3,})?$", name)
    vendor = m[1]

    if vendor is None:
        score = 10
    else:
        score = 20 + vendor_get_sort_score(vendor)

    return (score, name)

def __feature_struct_get_sort_score(name):
    m = re.match(r"^VkPhysicalDevice(Vulkan\w+)?Features$", name)
    if m is not None:
        if m[1] is None:
            return 10
        else:
            return 20

    m = re.match(r"^Vk\w+Features([A-Z]{3,})?$", name)
    if m is not None:
        vendor = m[1]
        if vendor is None:
            return 30
        else:
            return 40 + vendor_get_sort_score(vendor)

    return 50

def feature_struct_sort_key(name: str):
    """Key for sorting names of Vulkan feature structs."""
    score = __feature_struct_get_sort_score(name)
    return (score, name)

def __property_struct_get_sort_score(name):
    m = re.match(r"^VkPhysicalDevice(Vulkan\w+)?Properties$", name)
    if m is not None:
        if m[1] is None:
            return 10
        else:
            return 20

    m = re.match(r"^Vk\w+Properties([A-Z]{3,})?$", name)
    if m is not None:
        vendor = m[1]
        if vendor is None:
            return 30
        else:
            return 40 + vendor_get_sort_score(vendor)

    return 50

def property_struct_sort_key(name: str):
    """Key for sorting names of Vulkan property structs."""
    score = __property_struct_get_sort_score(name)
    return (score, name)

class XmlError(RuntimeError):

    message: str
    element: Optional[ET.Element]

    def __init__(self, message=None, *, element=None):
        if message:
            self.message = message
        else:
            if element is None:
                raise ValueError("if `message` is empty, then `element` must not be None")
            self.message = "error in XML element"

        self.element = element

    def __str__(self):
        s = StringIO()
        s.write(self.message)

        if self.element is not None:
            s.write("\n")
            s.write(ET.tostring(self.element, encoding="unicode"))

        return s.getvalue()

class LimitType(enum.StrEnum):
    """XML attribute 'limittype'."""

    @classmethod
    def from_xml(cls, x: str):
        match x:
            case "not_":
                raise KeyError
            case "not":
                return cls.not_
            case _:
                return cls[x]

    bitmask = enum.auto()
    bits = enum.auto()
    exact = enum.auto()
    max = enum.auto()
    min = enum.auto()
    mul = enum.auto()
    noauto = enum.auto()
    not_ = "not"
    pot = enum.auto()
    range = enum.auto()
    struct = enum.auto()

    def to_json_obj(self):
        return self._value_


@dataclass(frozen=True)
class LimitKey:

    struct: str
    member: str

    def __post_init__(self):
        if "." in self.struct:
            raise ValueError(f"bad struct name {self.struct!r}")
        if "." in self.member:
            raise ValueError(f"bad member name {self.member!r}")

    def to_json_key(self):
        return f"{self.struct}.{self.member}"

@dataclass(frozen=True)
class Limit:

    _: KW_ONLY
    struct: str
    member: str
    type: str
    limit_types: [LimitType]

    LIMIT_TYPE_SLOTS = (
        (
            LimitType.bitmask,
            LimitType.bits,
            LimitType.exact,
            LimitType.max,
            LimitType.min,
            LimitType.noauto,
            LimitType.not_,
            LimitType.range,
            LimitType.struct,
        ),
        (
            LimitType.mul,
            LimitType.pot,
        ),
    )

    def __raise_unexpected_limit_type(self):
        s = ",".join(self.limit_types)
        raise XmlError("unexpected @limittype={s!r}")

    def __post_init__(self):
        cls = self.__class__
        n = len(self.limit_types)

        if n == 0:
            raise XmlError("empty @limittype")

        if self.limit_types[0] not in cls.LIMIT_TYPE_SLOTS[0]:
            self.__raise_unexpected_limit_type()

        if n >= 2:
            if self.limit_types[1] not in cls.LIMIT_TYPE_SLOTS[1]:
                self.__raise_unexpected_limit_type()

        if n >= 3:
            self.__raise_unexpected_limit_type()

    @property
    def key(self) -> LimitKey:
        return LimitKey(self.struct, self.member)

    def to_json_obj(self):
        return {
            "struct": self.struct,
            "member": self.member,
            "type": self.type,
            "limit_types": [x.to_json_obj() for x in self.limit_types],
        }

    def merge_values(self, dst, src) -> Any:
        assert isinstance(dst, list) == isinstance(src, list)

        match self.limit_types[0]:
            case LimitType.bitmask:
                return dst | src
            case LimitType.bits:
                assert isinstance(dst, Number)
                assert isinstance(src, Number)
                return max(dst, src)
            case LimitType.exact:
                raise NotImplementedError # TODO
            case LimitType.max:
                if isinstance(dst, list):
                    assert len(dst) == len(src)
                    return [max(dst[i], src[i]) for i in range(len(dst))]
                else:
                    return max(dst, src)
            case LimitType.min:
                if isinstance(dst, list):
                    assert len(dst) == len(src)
                    return [min(dst[i], src[i]) for i in range(len(dst))]
                else:
                    return min(dst, src)
            case LimitType.noauto:
                raise NotImplementedError # TODO
            case LimitType.not_:
                return dst and src
            case LimitType.range:
                return [min(dst[0], src[0]), max(dst[1], src[1])]
            case LimitType.struct:
                raise NotImplementedError # TODO
            case _:
                assert False

@dataclass
class TypeInfo:
    """Info for Vulkan type."""
    pass

@dataclass
class MemberInfo(TypeInfo):
    """Info for Vulkan struct member."""

    _: KW_ONLY
    name: str

    base_type: str
    """The base type is only the text inside the <type> element. That is, it contains not pointer or
    array info.
    """

    def to_json_obj(self):
        return {
            "name": self.name,
            "base_type": self.base_type,
        }

@dataclass
class StructInfo(TypeInfo):
    """Info for Vulkan struct."""

    _: KW_ONLY
    name: str
    members: dict[str, MemberInfo]

    def to_json_obj(self):
        return {
            "name": self.name,
            "members": [
                x.to_json_obj()
                for x in self.members.values()
            ],
        }

class RegistryXML:
    """
    XML registry data.

    Normally, this is the data from a single `vk.xml` file. However, data from multiple files can be
    added with method `add_file`. For example, this may include data from `video.xml` and from
    custom xml files too.
    """

    aliases: dict[str, str]
    """Maps @name to @alias for each XML element with attribute @alias. That is, each item pair is
    `(old_name, new_name)`.
    """

    limits: dict[LimitKey, Limit]
    struct_info: dict[str, StructInfo]
    
    def __init__(self):
        self.aliases = {}
        self.limits = {}
        self.struct_info = {}

    def add_file(self, file: PathLike) -> None:
        etree: ET.ElementTree = ET.parse(file)

        reg_elem = etree.getroot()
        if reg_elem.tag != "registry":
            raise XmlError(f"root element has tag {reg_elem.tag!r}, expected 'registry'")

        self.__parse_aliases(reg_elem)
        self.__parse_limit_types(reg_elem)
        self.__parse_struct_info(reg_elem)

    def __parse_aliases(self, reg_elem: ET.Element) -> None:
        assert reg_elem.tag == "registry"

        for e in reg_elem.iterfind(".//*[@name][@alias]"):
            name = e.get("name")
            assert name

            alias = e.get("alias")
            assert alias

            self.aliases[name] = alias

    def __parse_limit_types(self, reg_elem: ET.Element) -> None:
        assert reg_elem.tag == "registry"

        # For each <type> that has a <member> with @limittype...
        #
        # (These are the only valid instances of @limittype).
        for struct_elem in reg_elem.iterfind(".//type//member[@limittype]/.."):
            if "struct" != struct_elem.get("category"):
                raise XmlError("only <type> elements with @category='struct' can have "
                               "a <member> with @limittype",
                               element=struct_elem)

            struct_name = struct_elem.get("name")
            if struct_name is None:
                raise XmlError("<type> must have @name", element=struct_elem)

            for member_elem in struct_elem.iterfind(".//member[@limittype]"):
                def raise_invalid_member():
                    raise XmlError("invalid <member> data", element=member_elem)

                i = iter(member_elem)

                try:
                    type_elem = next(i)
                    if type_elem.tag != "type":
                        raise_invalid_member()

                    name_elem = next(i)
                    if name_elem.tag != "name":
                        raise_invalid_member()
                except StopIteration:
                    raise_invalid_member()

                limit_types = []
                for x in member_elem.get("limittype").split(","):
                    try:
                        limit_types.append(LimitType.from_xml(x))
                    except LookupError:
                        raise XmlError(f"unknown limittype {x!r} in struct",
                                       element=struct_elem)

                limit = Limit(
                    struct = struct_name,
                    member = name_elem.text.strip(),
                    type = type_elem.text.strip(),
                    limit_types = limit_types,
                )

                self.limits[limit.key] = limit

    def __parse_struct_info(self, reg_elem: ET.Element) -> None:
        assert reg_elem.tag == "registry"

        for struct_elem in reg_elem.iterfind(".//type[@category='struct']"):
            struct_name = struct_elem.get("name")
            if struct_name is None:
                raise XmlError("<type> must have @name", element=struct_elem)

            if struct_name in self.struct_info:
                _log.warn(f"XML redefines struct {struct_name!r}")

            if struct_elem.get("alias") is not None:
                continue

            member_infos = {}
            for member_elem in struct_elem.iterfind("./member"):
                def raise_invalid_member():
                    raise XmlError("invalid <member> data", element=member_elem)

                i = iter(member_elem)

                try:
                    type_elem = next(i)
                    if type_elem.tag != "type":
                        raise_invalid_member()

                    name_elem = next(i)
                    if name_elem.tag != "name":
                        raise_invalid_member()
                except StopIteration:
                    raise_invalid_member()

                name = name_elem.text
                member_infos[name] = MemberInfo(name = name,
                                                base_type = type_elem.text)

            self.struct_info[struct_name] = \
                    StructInfo(name = struct_name,
                               members = member_infos)

    def get_limit(self, struct: str, member: str) -> LimitType:
        key = LimitKey(struct, member)
        return self.limits[key]

    def to_json_obj(self):
        return {
            "aliases": self.aliases,
            "limits": {
                k.to_json_key(): v.to_json_obj()
                for k, v in self.limits.items()
            },
            "struct_info": [
                x.to_json_obj()
                for x in self.struct_info.values()
            ],
        }

def normalize_vk_name(xml: RegistryXML, name: str) -> str:
    """
    Normalize a name in the Vulkan API.

    If the name has been deprecated in favor of a new name, then return the new name. Otherwise,
    return the name as-is.
    """
    while True:
        next_name = xml.aliases.get(name)
        if next_name is None:
            return name
        name = next_name

def normalize_vk_names_deep(xml: RegistryXML, json_obj: Any, json_path: str) -> Any:
    """
    Recursively normalize all Vulkan names in read-only json object.

    See `normalize_vk_name`.

    The `json_path` is used in error messages, and so should be the path _before_ normalization is
    applied.
    """

    obj = json_obj

    if obj is None:
        return obj
    elif isinstance(obj, dict):
        return {
            normalize_vk_name(xml, k): \
                normalize_vk_names_deep(xml, v, f"{json_path}.{k}")
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [
            normalize_vk_names_deep(xml, v, f"{json_path}[{i}]")
            for i, v in enumerate(obj)
        ]
    elif isinstance(obj, str):
        return normalize_vk_name(xml, obj)
    elif isinstance(obj, bool):
        return obj
    elif isinstance(obj, Number):
        return obj
    else:
        raise ValueError(f"json value at {json_path!r} has unexpected type {type(obj)}")

def struct_to_json_obj(xml: RegistryXML, struct_name: str, struct_obj: dict) -> dict:
    """In the result, the members have the same order as in the XML."""

    struct_name_normal = normalize_vk_name(xml, struct_name)

    struct_info = xml.struct_info.get(struct_name_normal)
    if struct_info is None:
        _log.warn(f"struct_to_json_obj: unknown struct name {struct_name!r}")
        return struct_obj

    new_obj = {}

    # struct_obj may be incomplete, as is usual for Vulkan profiles.
    # Preserve its incompleteness.
    for member_name, member_info in struct_info.members.items():
        member_value = struct_obj.get(member_name)

        # Skip members that are missing from the original struct obj.
        if member_value is None:
            continue

        member_type_normal = normalize_vk_name(xml, member_info.base_type)
        member_is_struct = (xml.struct_info.get(member_type_normal) is not None)
        if member_is_struct:
            member_value = struct_to_json_obj(xml, member_type_normal, member_value)

        new_obj[member_name] = member_value

    if debug:
        old_members = set(struct_obj.keys())
        new_members = set(new_obj.keys())
        missing_members = old_members - new_members
        if missing_members:
            lost = ", ".join(map(repr, missing_members))
            _log.error(f"when formatting struct {struct_name!r}, members were lost: {lost}")

    return new_obj
