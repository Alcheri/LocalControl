#!/usr/bin/env python3
"""Check optional LocalControl GUI dependencies."""

from __future__ import annotations

import importlib.util
import shutil
import sys

REQUIRED_MODULES = {
    "bandit": "bandit",
    "sv-ttk": "sv_ttk",
}


def main() -> int:
    missing = []
    for package_name, module_name in REQUIRED_MODULES.items():
        if importlib.util.find_spec(module_name) is None:
            missing.append(package_name)

    if shutil.which("ssh.exe") is None and shutil.which("ssh") is None:
        missing.append("OpenSSH client")

    if not missing:
        print("All GUI requirements are importable.")
        return 0

    print("Missing GUI requirements: %s" % ", ".join(missing), file=sys.stderr)
    print(
        "Install Python packages with: python -m pip install -r tools/requirements.txt",
        file=sys.stderr,
    )
    print(
        "Install the OpenSSH client with your platform package manager if it is missing.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
