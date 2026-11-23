"""Run the actual configuration generator in a temporary, private package."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DeploymentConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copy2(ROOT / "configure.py", self.root)
        for platform in ("QNAP", "Synology"):
            target = self.root / platform / "nas"
            target.mkdir(parents=True)
            shutil.copy2(ROOT / platform / "nas/deployment.json", target)

    def run_config(self, *args):
        return subprocess.run([sys.executable, "-X", "utf8", str(self.root / "configure.py"),
                               "--contact-name", "Testteam", "--contact-reach", "test@example.invalid", *args],
                              capture_output=True, encoding="utf-8", cwd=self.temp.name)

    def read_config(self, platform):
        folder = self.root / platform
        env = dict(line.split("=", 1) for line in (folder / ".env").read_text().splitlines())
        server = json.loads((folder / "config/server.json").read_text(encoding="utf-8"))
        devices = [json.loads(file.read_text()) for file in sorted((folder / "config").glob("terminal-*.json"))]
        return env, server, devices

    def test_qnap_defaults_and_device_profiles_agree(self):
        result = self.run_config("--deployment", "qnap", "--nas-ip", "192.168.3.110")
        self.assertEqual(result.returncode, 0, result.stderr)
        env, server, devices = self.read_config("QNAP")
        self.assertEqual((env["KASSE_BIND_IP"], env["KASSE_PORT"]), ("192.168.3.110", "18443"))
        self.assertEqual(server["deployment"], "qnap")
        for device in devices:
            self.assertEqual(device["origin"], server["origin"])
            self.assertEqual(device["ca_file"], "/etc/kaffeekasse-terminal/nas-root.crt")
            self.assertEqual(device["token"], server["terminals"][device["terminal"]]["token"])
        self.assertEqual([device["terminal"] for device in devices], ["a"])
        self.assertFalse((self.root / "Synology/.env").exists())
        if os.name != "nt":
            self.assertEqual((self.root / "QNAP/.env").stat().st_mode & 0o777, 0o600)

    def test_synology_origin_and_proxy_settings(self):
        result = self.run_config("--deployment", "synology", "--origin", "https://kostbar.example.org")
        self.assertEqual(result.returncode, 0, result.stderr)
        env, server, devices = self.read_config("Synology")
        self.assertEqual(env["KASSE_AUTHORITY"], "kostbar.example.org")
        self.assertEqual(env["KASSE_DSM_PORT"], "18765")
        self.assertEqual(len(env["KASSE_DSM_PROXY_KEY"]), 64)
        self.assertEqual(server["deployment"], "synology")
        self.assertTrue(all(d["ca_file"] is None and d["origin"] == server["origin"] for d in devices))
        self.assertNotIn("KASSE_BIND_IP", env)
        self.assertFalse((self.root / "QNAP/.env").exists())

    def test_custom_synology_origin_is_not_hardcoded(self):
        result = self.run_config("--deployment", "synology", "--origin", "https://other.example.invalid:9443")
        self.assertEqual(result.returncode, 0, result.stderr)
        env, server, devices = self.read_config("Synology")
        self.assertEqual(env["KASSE_AUTHORITY"], "other.example.invalid:9443")
        self.assertTrue(all(d["origin"] == server["origin"] for d in devices))

    def test_optional_second_profile_and_custom_reader_ca(self):
        result = self.run_config("--deployment", "synology", "--origin", "https://kostbar.example.org",
                                 "--label-b", "Zweiter Verkaufspunkt", "--reader-ca")
        self.assertEqual(result.returncode, 0, result.stderr)
        _, server, devices = self.read_config("Synology")
        self.assertEqual([device["terminal"] for device in devices], ["a", "b"])
        self.assertEqual(server["terminals"]["b"]["label"], "Zweiter Verkaufspunkt")
        self.assertNotEqual(devices[0]["token"], devices[1]["token"])
        self.assertTrue(all(d["ca_file"] == server["reader_ca_file"] for d in devices))

    def test_missing_qnap_ip_and_wrong_synology_ip_are_rejected(self):
        for args in (("--deployment", "qnap"),
                     ("--deployment", "synology", "--origin", "https://kostbar.example.org", "--nas-ip", "192.168.3.110")):
            self.assertNotEqual(self.run_config(*args).returncode, 0)
        self.assertFalse(list(self.root.glob("*/.env")))

    def test_synology_origin_must_be_explicit(self):
        result = self.run_config("--deployment", "synology")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--origin", result.stderr)
        self.assertFalse((self.root / "Synology/.env").exists())

    def test_deployment_must_be_explicit(self):
        self.assertNotEqual(self.run_config().returncode, 0)
        self.assertFalse(list(self.root.glob("*/.env")))

    def test_second_run_keeps_existing_keys_and_profiles(self):
        args = ("--deployment", "qnap", "--nas-ip", "192.168.3.110")
        self.assertEqual(self.run_config(*args).returncode, 0)
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertNotEqual(self.run_config(*args).returncode, 0)
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_invalid_origin_writes_no_configuration(self):
        for origin in ("http://insecure.invalid", "https://example.invalid/path", "https://example.invalid:443"):
            self.assertNotEqual(self.run_config("--deployment", "synology", "--origin", origin).returncode, 0)
        self.assertFalse(list(self.root.glob("*/.env")))


if __name__ == "__main__":
    unittest.main()
