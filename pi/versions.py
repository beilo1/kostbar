"""Collect an allowlisted package inventory from the Raspberry Pi."""
import subprocess

PI_PACKAGES = ("chromium", "python3", "python3-pyscard", "pcscd", "libccid", "pcsc-tools",
               "lightdm", "labwc", "wlr-randr", "curl", "unzip", "libnss3-tools", "util-linux", "usbguard",
               "network-manager")


def installed_packages():
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Package}\t${Status}\t${Version}\n", *PI_PACKAGES],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    versions = {}
    for line in result.stdout.splitlines():
        name, status, version = line.split("\t")
        if status == "install ok installed":
            versions[name] = version
    return versions
