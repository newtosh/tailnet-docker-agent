"""Allowlist policy: which containers are visible and which actions are permitted."""

from typing import Any

ACTIONS = frozenset({"start", "stop", "restart"})


class Policy:
    def __init__(self, containers: dict[str, set[str]]) -> None:
        self._containers = containers

    def names(self) -> list[str]:
        return sorted(self._containers)

    def can_read(self, name: str) -> bool:
        return name in self._containers

    def can_act(self, name: str, action: str) -> bool:
        return action in self._containers.get(name, set())


def policy_from_config(cfg: dict[str, Any]) -> Policy:
    containers: dict[str, set[str]] = {}
    for entry in cfg.get("containers", []):
        actions = set(entry.get("actions", []))
        unknown = actions - ACTIONS
        if unknown:
            raise ValueError(f"{entry['name']}: unknown actions {sorted(unknown)}")
        containers[entry["name"]] = actions
    return Policy(containers)
