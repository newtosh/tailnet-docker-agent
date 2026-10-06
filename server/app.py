"""MCP server exposing a fixed, allowlisted set of Docker operations."""

import logging
import os
import sys
from pathlib import Path

import docker
import yaml
from mcp.server.fastmcp import FastMCP

from policy import policy_from_config

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(message)s")
log = logging.getLogger("stack-agent")

CFG = yaml.safe_load(Path(os.environ.get("AGENT_CONFIG", "/config/agent.yaml")).read_text())
POLICY = policy_from_config(CFG)
client = docker.DockerClient(base_url=os.environ.get("DOCKER_HOST", "tcp://socket-proxy:2375"))
mcp = FastMCP(
    CFG["agent"]["name"],
    host="0.0.0.0",
    port=int(CFG["agent"].get("mcp_port", 8000)),
)

MAX_TAIL = 500


def _read(name: str):  # type: ignore[no-untyped-def]
    if not POLICY.can_read(name):
        raise ValueError(f"container not allowlisted: {name}")
    return client.containers.get(name)


def _act(name: str, action: str) -> str:
    if not POLICY.can_act(name, action):
        log.info("denied action=%s container=%s", action, name)
        raise ValueError(f"action '{action}' not permitted for {name}")
    container = _read(name)
    getattr(container, action)()
    log.info("action=%s container=%s", action, name)
    return f"{action} sent to {name}"


@mcp.tool()
def list_containers() -> list[dict[str, str]]:
    """List allowlisted containers with run state and health."""
    rows = []
    for name in POLICY.names():
        c = _read(name)
        health = c.attrs.get("State", {}).get("Health", {}).get("Status", "none")
        rows.append({"name": name, "status": c.status, "health": health})
    return rows


@mcp.tool()
def status(name: str) -> dict[str, str]:
    """Run state and health for one allowlisted container."""
    c = _read(name)
    health = c.attrs.get("State", {}).get("Health", {}).get("Status", "none")
    return {"name": name, "status": c.status, "health": health}


@mcp.tool()
def logs(name: str, tail: int = 100) -> str:
    """Last N log lines for one allowlisted container (max 500)."""
    tail = max(1, min(tail, MAX_TAIL))
    return _read(name).logs(tail=tail).decode("utf-8", errors="replace")


@mcp.tool()
def start(name: str) -> str:
    """Start an allowlisted container (requires the start action in config)."""
    return _act(name, "start")


@mcp.tool()
def stop(name: str) -> str:
    """Stop an allowlisted container (requires the stop action in config)."""
    return _act(name, "stop")


@mcp.tool()
def restart(name: str) -> str:
    """Restart an allowlisted container (requires the restart action in config)."""
    return _act(name, "restart")


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
