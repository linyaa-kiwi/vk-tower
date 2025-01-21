# Copyright 2025 Google
# SPDX-License-Identifier: MIT

from copy import copy
from dataclasses import dataclass, KW_ONLY
import enum
from io import StringIO
from os import PathLike
from typing import Optional
import xml.etree.ElementTree as ET

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

class RegistryXML:
    """
    XML registry data.

    Normally, this is the data from a single `vk.xml` file. However, data from multiple files can be
    added with method `add_file`. For example, this may include data from `video.xml` and from
    custom xml files too.
    """

    aliases: dict[str, str]
    """Maps @alias to @name for each XML element with attribute @alias."""

    limits: dict[LimitKey, Limit]
    
    def __init__(self):
        self.aliases = {}
        self.limits = {}

    def add_file(self, file: PathLike) -> None:
        etree: ET.ElementTree = ET.parse(file)

        reg_elem = etree.getroot()
        if reg_elem.tag != "registry":
            raise XmlError(f"root element has tag {reg_elem.tag!r}, expected 'registry'")

        self.__parse_aliases(reg_elem)
        self.__parse_limit_types(reg_elem)

    def __parse_aliases(self, reg_elem: ET.Element) -> None:
        assert reg_elem.tag == "registry"

        for e in reg_elem.iterfind(".//*[@name][@alias]"):
            self.aliases[e.get("alias")] = e.get("name")

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

    def normalize_vk_name(self, name: str) -> str:
        assert isinstance(name, str)

        while True:
            next_name = self.aliases.get(name)
            if next_name is None:
                return name
            name = next_name

    def to_json_obj(self):
        return {
            "aliases": self.aliases,
            "limits": {
                k.to_json_key(): v.to_json_obj()
                for k, v in self.limits.items()
            },
        }
