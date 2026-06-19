#!/usr/bin/env bash

set -euo pipefail

repo_root="$(pwd)"
python_bin=""

if [[ "${1-}" == "--no-venv" ]]; then
    python_bin="python3"
else
    venv_path="$repo_root/.venv-linux"
    python_bin="$venv_path/bin/python"

    if [[ ! -x "$python_bin" ]]; then
        python3 -m venv "$venv_path"
    fi
fi

"$python_bin" -m pip install --upgrade pip
"$python_bin" -m pip install -r requirements.txt -r requirements-build.txt
"$python_bin" -m PyInstaller \
    --clean \
    --noconfirm \
    --onefile \
    --name LocalControl-GUI \
    botctl_gui_linux.py

printf 'Built dist/LocalControl-GUI\n'
