# tailnet-docker-agent

A small MCP server that lets an AI agent see and control a fixed allowlist of Docker
containers on one host, reachable only over your Tailscale tailnet.

Design: the agent never touches the Docker socket directly. Two layers enforce the
allowlist, generated from one config file:

1. **MCP server** (`server/`): exposes `list_containers`, `status`, `logs`, `start`,
   `stop`, `restart`. Refuses anything not in the config.
2. **socket-proxy** ([wollomatic/socket-proxy](https://github.com/wollomatic/socket-proxy)):
   regex allowlist on the Docker API. Only the read endpoints and the
   start/stop/restart paths for listed containers are open. `POST /containers/create`
   and `exec` are never allowed, since either would give host root.

The MCP server sits on an internal Docker network with no route out. Only a Tailscale
sidecar bridges it to the tailnet, via `tailscale serve`.

Run one instance per host. Each instance manages only its local containers, so if one
host goes down the other keeps working.

## Quick start

```bash
cp config/agent.example.yaml config/agent.yaml   # edit names, actions, docker_gid
cp .env.example .env                              # set TS_AUTH_KEY
make test                                         # policy and render checks
make up                                           # render + build + start
```

Then point your MCP client at `https://<tailnet_hostname>.<tailnet>.ts.net/mcp`.

## Making it yours

- Add containers in `config/agent.yaml`. Grant actions per container; default is read-only.
- Re-run `make render` after any config change, then `make up`.
- Add a new tool: write it in `server/app.py`, gate it through `policy.py`, and add a test.
- Keep real hostnames, auth keys, and container names out of this repo. Put your
  real `config/agent.yaml` in a private repo or a secrets store.

## Not in scope

- Compose up / image pull. Creating containers is root-equivalent on the host, so change
  deployments through your normal repo and deploy path.
- Cross-host failover. Each host manages its own containers.

## Caveats (verify before relying on them)

- The socket-proxy regex is matched against the request path. Confirm that `logs` calls
  with query strings match the GET rule in your environment.
- `docker_gid` must match the group owning the Docker socket on the host. On macOS
  (Docker Desktop) the socket is inside the VM; check the group before starting.
- Mounting the Docker socket to any container is powerful. Only the socket-proxy does it here.
