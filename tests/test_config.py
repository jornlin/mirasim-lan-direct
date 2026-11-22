import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mld import config, hostinfo  # noqa: E402


PAIR = {
    "ok": True,
    "token": "tok123456789",
    "e2e": "e2epublic",
    "hosts": ["http://192.168.1.50:4939", "http://10.0.0.5:4939"],
    "cloudAttach": {"nodeId": "pc-0123456789abcdef"},
    "machine": "host-a",
}


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = os.environ.get("MLD_CONFIG_DIR")
        os.environ["MLD_CONFIG_DIR"] = self.tmp.name

    def tearDown(self):
        if self.env is None:
            os.environ.pop("MLD_CONFIG_DIR", None)
        else:
            os.environ["MLD_CONFIG_DIR"] = self.env
        self.tmp.cleanup()

    def test_save_load_and_permissions(self):
        cfg = {"version": 1, "targets": [config.entry_from_pair(PAIR)]}
        config.save(cfg)
        self.assertEqual(config.load()["targets"][0]["nodeId"], "pc-0123456789abcdef")
        if os.name == "posix":
            mode = stat.S_IMODE(config.config_path().stat().st_mode)
            self.assertEqual(mode, 0o600)

    def test_sanitized_masks_secrets(self):
        cfg = {"targets": [config.entry_from_pair(PAIR)]}
        shown = config.sanitized(cfg)
        self.assertNotEqual(shown["targets"][0]["token"], "tok123456789")
        self.assertTrue(shown["targets"][0]["token"].endswith("…"))

    def test_entry_from_pair_requires_cloud_node(self):
        bad = dict(PAIR)
        bad["cloudAttach"] = {}
        bad.pop("nodeId", None)
        with self.assertRaises(ValueError):
            config.entry_from_pair(bad)

    def test_pair_refresh_preserves_user_choices(self):
        old = config.entry_from_pair(PAIR)
        old.update({
            "label": "my-host",
            "mode": "hybrid",
            "collab": True,
            "grant": "jwt",
            "member": True,
            "installId": "mld-abc",
            "origin": "http://10.0.0.5:4939",
            "token": "old-token",
        })
        merged = config.merge_pair_entry(old, config.entry_from_pair(PAIR))
        for key, value in (("label", "my-host"), ("mode", "hybrid"),
                           ("collab", True), ("grant", "jwt"),
                           ("member", True), ("installId", "mld-abc")):
            self.assertEqual(merged[key], value, key)
        # Host-derived data is refreshed, and the origin is re-resolved.
        self.assertEqual(merged["token"], "tok123456789")
        self.assertEqual(merged["hosts"], PAIR["hosts"])
        self.assertEqual(merged["origin"], "")

    def test_host_normalisation(self):
        self.assertEqual(hostinfo.split_host("10.0.0.5:5000"), ("10.0.0.5", 5000))
        self.assertEqual(hostinfo.split_host("http://10.0.0.5:5000/x"), ("10.0.0.5", 5000))
        self.assertEqual(hostinfo.split_host("host.example"), ("host.example", 4939))
        self.assertEqual(hostinfo.origin_for("ws://host:1234/x"), "http://host:1234")

    def test_choose_origin_returns_first_when_none_reachable(self):
        # 192.0.2.0/24 is TEST-NET-1: guaranteed not to reach a listener here.
        chosen = hostinfo.choose_origin(["http://192.0.2.1:9", "http://192.0.2.2:9"])
        self.assertEqual(chosen, "http://192.0.2.1:9")


if __name__ == "__main__":
    unittest.main()