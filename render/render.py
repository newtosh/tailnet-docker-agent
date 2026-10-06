#!/usr/bin/env python3
"""Render generated/ (compose file, Tailscale serve config) from config/agent.yaml.

The socket-proxy allowlist is derived from the same config as the MCP server's
policy, so the two layers cannot drift apart.
"""

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

VERSION = r"(/v[0-9.]+)?"
MUTATING = ("start", "stop", "restart")
ROOT = Path(__file__).resolve().parent.parent


def _alt(names: list[str]) -> str:
    return "(" + "|".join(re.escape(n) for n in names) + ")"


def proxy_flags(cfg: dict[str, Any]) -> list[str]:
    """Socket-proxy allowlist: reads for listed containers, mutations per action."""
    containers = cfg["containers"]
    names = [c["name"] for c in containers]
    flags = [
        f"-allowGET={VERSION}/(version|_ping)",
        f"-allowGET={VERSION}/containers/json",
    ]
    if names:
        flags.append(f"-allowGET={VERSION}/containers/{_alt(names)}/(json|logs)")
    for action in MUTATING:
        allowed = [c["name"] for c in containers if action in c.get("actions", [])]
        if allowed:
            flags.append(f"-allowPOST={VERSION}/containers/{_alt(allowed)}/{action}")
    return flags


def compose(cfg: dict[str, Any], out: Path, config_path: Path) -> dict[str, Any]:
    """Compose file for `out`. Paths are relative to `out`, so the output can be dropped anywhere."""
    a = cfg["agent"]
    # Local build from this repo by default; set agent.build to a git URL (e.g. pinned tag) to pull instead.
    build = a.get("build", os.path.relpath(ROOT / "server", out))
    config_mount = os.path.relpath(config_path, out)
    proxy_cmd = [
        "-loglevel=info",
        "-listenip=0.0.0.0",
        "-allowfrom=stack-agent",
        "-allowhealthcheck=true",
        *proxy_flags(cfg),
    ]
    return {
        "networks": {
            # Internal: no route out. Only the proxy and MCP server live here.
            "agentnet": {"name": "agentnet", "internal": True},
        },
        "services": {
            "tailscale-agent": {
                "image": "tailscale/tailscale:latest",
                "container_name": "tailscale-agent",
                "hostname": a["tailnet_hostname"],
                "restart": "unless-stopped",
                "cap_add": ["NET_ADMIN", "NET_RAW"],
                "devices": ["/dev/net/tun:/dev/net/tun"],
                "environment": {
                    "TS_AUTH_KEY": "${TS_AUTH_KEY}",
                    "TS_STATE_DIR": "/var/lib/tailscale",
                    "TS_SERVE_CONFIG": "/config/serve.json",
                },
                "volumes": [
                    "./state/tailscale:/var/lib/tailscale",
                    "./serve.json:/config/serve.json:ro",
                ],
                # Needs the internet for the tailnet control plane, so also on the default network.
                "networks": ["agentnet", "default"],
                "healthcheck": {
                    "test": ["CMD", "tailscale", "status"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3,
                    "start_period": "30s",
                },
            },
            "socket-proxy": {
                "image": "wollomatic/socket-proxy:1.13.1",
                "container_name": "agent-socket-proxy",
                "restart": "unless-stopped",
                "user": f"65534:{a['docker_gid']}",
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "command": proxy_cmd,
                "volumes": ["/var/run/docker.sock:/var/run/docker.sock:ro"],
                "networks": ["agentnet"],
                "healthcheck": {
                    "test": ["CMD", "./healthcheck"],
                    "interval": "10s",
                    "timeout": "5s",
                    "retries": 2,
                },
            },
            "stack-agent": {
                "build": build,
                "container_name": "stack-agent",
                "restart": "unless-stopped",
                "read_only": True,
                "tmpfs": ["/tmp"],
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "environment": {
                    "DOCKER_HOST": "tcp://socket-proxy:2375",
                    "AGENT_CONFIG": "/config/agent.yaml",
                },
                "volumes": [f"{config_mount}:/config/agent.yaml:ro"],
                "networks": ["agentnet"],
                "depends_on": ["socket-proxy"],
                "healthcheck": {
                    "test": [
                        "CMD",
                        "python",
                        "-c",
                        f"import socket; socket.create_connection(('localhost', {a.get('mcp_port', 8000)}), 2)",
                    ],
                    "interval": "30s",
                    "timeout": "5s",
                    "retries": 3,
                },
            },
        },
    }


def serve_config(cfg: dict[str, Any]) -> dict[str, Any]:
    port = cfg["agent"].get("mcp_port", 8000)
    return {
        "TCP": {"443": {"HTTPS": True}},
        "Web": {
            "${TS_CERT_DOMAIN}:443": {
                "Handlers": {"/mcp": {"Proxy": f"http://stack-agent:{port}/mcp"}}
            }
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "config" / "agent.yaml"))
    parser.add_argument("--out", default=str(ROOT / "generated"))
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "docker-compose.yml").write_text(
        yaml.safe_dump(compose(cfg, out, Path(args.config).resolve()), sort_keys=False)
    )
    (out / "serve.json").write_text(json.dumps(serve_config(cfg), indent=2) + "\n")
    print(f"rendered {out}")


if __name__ == "__main__":
    main()
