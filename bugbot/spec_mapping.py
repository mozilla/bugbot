# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

# mypy: disallow-untyped-defs
"""Map web specification URLs to Bugzilla (product, component) pairs."""

import itertools
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Self
from urllib.parse import SplitResult, urlsplit

import yaml

ProductComponent = tuple[str, str]


@dataclass
class RuleMatch:
    """A resolved (product, component)"""

    position: tuple[int, int]
    product: str
    component: str

    def __gt__(self, other: "RuleMatch") -> bool:
        return (self.position[0], -self.position[1]) > (
            other.position[0],
            -other.position[1],
        )


_order = itertools.count()


class Rule(ABC):
    level: int = 0

    def __init__(
        self,
        component: ProductComponent | None = None,
        paths: Sequence["Rule"] = (),
    ):
        self.component = component
        self.order = next(_order)

    @abstractmethod
    def get(self, parsed: SplitResult) -> RuleMatch | None:
        ...


class HostRule(Rule):
    level = 0

    def __init__(
        self,
        component: ProductComponent | None,
        paths: Sequence["PathRule"] = (),
    ):
        super().__init__(component)
        self.paths = paths

    def get(self, parsed: SplitResult) -> RuleMatch | None:
        for path_rule in self.paths:
            m = path_rule.get(parsed)
            if m is not None:
                return m
        if self.component is not None:
            return RuleMatch((self.level, self.order), *self.component)
        return None


class PathRule(Rule):
    level = 1

    def __init__(
        self,
        path: str | None,
        component: ProductComponent,
    ):
        self.path = re.compile(path) if path is not None else None
        super().__init__(component)

    def get(self, parsed: SplitResult) -> RuleMatch | None:
        if self.path is None or self.path.search(parsed.path) is not None:
            assert self.component is not None
            return RuleMatch((self.level, self.order), *self.component)
        return None


def parse_component(value: str) -> ProductComponent:
    if " :: " not in value:
        raise ValueError(f"Invalid component '{value}'")
    product, _, component = value.partition(" :: ")
    return product, component


class SpecMapper:
    def __init__(self, rules: dict[str, HostRule], default: ProductComponent):
        self.rules = rules
        self.default = default

    @classmethod
    def load(
        cls, path: str = os.path.join(os.path.dirname(__file__), "spec_mapping.yml")
    ) -> Self:
        with open(path) as f:
            data = yaml.safe_load(f)
        rules: dict[str, HostRule] = {}
        default: ProductComponent | None = None
        for entry in data:
            component = entry.get("component")
            if "host" not in entry:
                if default is not None:
                    raise ValueError(
                        f"Got multiple default components second in entry {entry}"
                    )
                default = parse_component(component)
                continue
            paths = [
                PathRule(path_entry["path"], parse_component(path_entry["component"]))
                for path_entry in entry.get("paths", [])
            ]
            rules[entry["host"]] = HostRule(
                parse_component(component) if component is not None else None,
                paths,
            )
        if default is None:
            raise ValueError("Missing default component")
        return cls(rules, default)

    def map_url(self, url: str) -> RuleMatch | None:
        """Return the most specific :class:`Match` for ``url``, or ``None``."""
        parsed = urlsplit(url)
        host_rule = self.rules.get(parsed.hostname or "")
        if host_rule is None:
            return None
        return host_rule.get(parsed)

    def map_urls(self, urls: Iterable[str]) -> ProductComponent:
        """Pick a plausible (product, component) for a feature with given spec URLs."""
        best_match: RuleMatch | None = None
        for url in urls:
            rule_match = self.map_url(url)
            if rule_match is None:
                continue
            if best_match is None or rule_match > best_match:
                best_match = rule_match
        if best_match is None:
            return self.default
        return best_match.product, best_match.component
