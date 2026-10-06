"""Checks for the policy and the rendered config. Run: make test"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "server"), str(ROOT / "render")]

from policy import policy_from_config  # noqa: E402
from render import compose, proxy_flags  # noqa: E402

CFG = {
    "agent": {"name": "t", "tailnet_hostname": "t", "mcp_port": 8000, "docker_gid": 999},
    "containers": [
        {"name": "web", "actions": ["restart"]},
        {"name": "db", "actions": []},
    ],
}


class PolicyTests(unittest.TestCase):
    def test_restart_only_where_granted(self):
        p = policy_from_config(CFG)
        self.assertTrue(p.can_act("web", "restart"))
        self.assertFalse(p.can_act("web", "stop"))
        self.assertFalse(p.can_act("db", "restart"))

    def test_unlisted_container_denied(self):
        p = policy_from_config(CFG)
        self.assertFalse(p.can_read("secret-app"))
        self.assertFalse(p.can_act("secret-app", "restart"))

    def test_unknown_action_rejected(self):
        bad = {"containers": [{"name": "x", "actions": ["exec"]}]}
        with self.assertRaises(ValueError):
            policy_from_config(bad)


class RenderTests(unittest.TestCase):
    def test_proxy_never_allows_create_or_exec(self):
        flags = " ".join(proxy_flags(CFG))
        self.assertNotIn("create", flags)
        self.assertNotIn("exec", flags)
        self.assertNotIn("images", flags)

    def test_restart_allowed_only_for_granted_name(self):
        flags = " ".join(proxy_flags(CFG))
        self.assertIn("-allowPOST=(/v[0-9.]+)?/containers/(web)/restart", flags)
        self.assertNotIn("/stop", flags)

    def test_mcp_server_has_no_socket_and_no_egress(self):
        svc = compose(CFG, Path("/x/out"), Path("/x/config/agent.yaml"))["services"]["stack-agent"]
        self.assertFalse(any("docker.sock" in v for v in svc.get("volumes", [])))
        self.assertEqual(svc["networks"], ["agentnet"])
        self.assertTrue(compose(CFG, Path("/x/out"), Path("/x/config/agent.yaml"))["networks"]["agentnet"]["internal"])


if __name__ == "__main__":
    unittest.main()
