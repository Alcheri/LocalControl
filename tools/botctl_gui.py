#!/usr/bin/env python3
"""Small Tkinter test GUI for LocalControl commands."""

from __future__ import annotations

import json
import os
import queue
import re
import shlex
import shutil
import socket
import subprocess  # nosec B404
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import ttk

APP_NAME = "localcontrol-gui"
IS_LINUX = sys.platform.startswith("linux")
SSH_EXECUTABLES = {"ssh", "ssh.exe"}


def _default_settings_file() -> str:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(
            Path.home() / "AppData" / "Roaming"
        )
        return str(Path(base) / "LocalControl GUI" / "botctl_gui.json")
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return str(Path(base) / APP_NAME / "botctl_gui.json")


def _environment_port(name: str, default: int) -> int:
    try:
        port = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    if port < 1 or port > 65535:
        return default
    return port


DEFAULT_SOCKET = os.path.expanduser(
    os.environ.get(
        "BOT_CONTROL_SOCKET",
        "~/runbot/plugins/LocalControl/.localcontrol.sock" if IS_LINUX else "",
    )
)
DEFAULT_MODE = "socket" if IS_LINUX else "ssh"
DEFAULT_HOST = os.environ.get("BOT_CONTROL_HOST", "127.0.0.1")
DEFAULT_PORT = _environment_port("BOT_CONTROL_PORT", 8023)
DEFAULT_SSH_HOST = os.environ.get("BOT_CONTROL_SSH_HOST", "")
DEFAULT_SSH_PORT = _environment_port("BOT_CONTROL_SSH_PORT", 22)
DEFAULT_SSH_USER = os.environ.get(
    "BOT_CONTROL_SSH_USER", os.environ.get("USER", "")
)
DEFAULT_SSH_COMMAND = os.environ.get("BOT_CONTROL_SSH_COMMAND", "")
DEFAULT_REMOTE_PATH = os.environ.get(
    "BOT_CONTROL_REMOTE_PATH", "~/runbot/plugins/LocalControl"
)
DEFAULT_EGGDROP_HOST = os.environ.get("EGGDROP_HOST", "127.0.0.1")
DEFAULT_EGGDROP_PORT = _environment_port("EGGDROP_PORT", 3333)
DEFAULT_EGGDROP_HANDLE = os.environ.get("EGGDROP_HANDLE", "Barry")
DEFAULT_EGGDROP_SSH_HOST = os.environ.get("EGGDROP_SSH_HOST", "")
DEFAULT_EGGDROP_SSH_PORT = _environment_port("EGGDROP_SSH_PORT", 22)
DEFAULT_EGGDROP_SSH_USER = os.environ.get("EGGDROP_SSH_USER", "")
DEFAULT_EGGDROP_REMOTE_HOST = os.environ.get(
    "EGGDROP_REMOTE_HOST", "127.0.0.1"
)
DEFAULT_EGGDROP_REMOTE_PORT = _environment_port(
    "EGGDROP_REMOTE_PORT", DEFAULT_EGGDROP_PORT
)
DEFAULT_EGGDROP_PROFILES = (
    {
        "name": "Direct",
        "ssh_tunnel": False,
    },
    {
        "name": "SSH tunnel",
        "ssh_tunnel": True,
    },
)
MAX_REPLY_BYTES = 65536
REPLY_CHUNK_BYTES = 4096
REQUEST_TIMEOUT_SECONDS = 10.0
SOCKET_READ_IDLE_SECONDS = 0.25
EGGDROP_READ_BYTES = 4096
PROBE_COMMAND = "list LocalControl"
DEFAULT_THEME = os.environ.get("BOT_CONTROL_GUI_THEME", "dark")
SETTINGS_FILE = Path(
    os.environ.get("BOT_CONTROL_GUI_SETTINGS", _default_settings_file())
)
DEFAULT_DIAGNOSTIC_LOG = str(
    Path(
        os.environ.get(
            "BOT_CONTROL_GUI_LOG", str(SETTINGS_FILE.with_suffix(".log"))
        )
    )
)
SETTINGS_FILE_MODE = 0o600
DIAGNOSTIC_LOG_MODE = 0o600
WINDOW_GEOMETRY_RE = re.compile(r"^\d+x\d+[+-]\d+[+-]\d+$")
SENSITIVE_COMMAND_TERMS = (
    "password",
    "passwd",
    "passphrase",
    "secret",
    "token",
    "apikey",
    "api_key",
)
SENSITIVE_COMMAND_KEYS = ("key",)
COMMAND_PRESETS = (
    "sysinfo",
    "version",
    "list LocalControl",
    "config plugins.LocalControl.tcpListenerEnabled",
    "config plugins.LocalControl.tcpListenHost",
    "config plugins.LocalControl.tcpListenPort",
    "say #test hello from LocalControl GUI",
)


class LocalControlGui:
    """Tiny LocalControl command sender for local testing."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.results: queue.Queue[tuple[bool, str, str, str]] = queue.Queue()
        self.eggdrop_events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.settings = _load_settings()
        self.command_history = _normalise_history(
            self.settings.get("command_history", [])
        )
        self.eggdrop_input_history = _normalise_eggdrop_history(
            self.settings.get("eggdrop_input_history", [])
        )
        self.eggdrop_history_index: int | None = None
        self.eggdrop_profile_names = _eggdrop_profile_names()
        self.ssh_user_history = _normalise_value_history(
            self.settings.get("ssh_user_history", []), DEFAULT_SSH_USER
        )
        self.ssh_host_history = _normalise_value_history(
            self.settings.get("ssh_host_history", []), DEFAULT_SSH_HOST
        )
        self.eggdrop_ssh_user_history = _normalise_value_history(
            self.settings.get("eggdrop_ssh_user_history", []),
            DEFAULT_EGGDROP_SSH_USER,
        )
        self.eggdrop_ssh_host_history = _normalise_value_history(
            self.settings.get("eggdrop_ssh_host_history", []),
            DEFAULT_EGGDROP_SSH_HOST,
        )
        self.eggdrop_remote_port_history = _normalise_value_history(
            self.settings.get("eggdrop_remote_port_history", []),
            str(DEFAULT_EGGDROP_REMOTE_PORT),
        )

        initial_mode = str(self.settings.get("mode", DEFAULT_MODE))
        if not IS_LINUX and initial_mode != "ssh":
            initial_mode = "ssh"
        self.mode_var = tk.StringVar(value=initial_mode)
        self.socket_var = tk.StringVar(
            value=self.settings.get("socket", DEFAULT_SOCKET)
        )
        self.host_var = tk.StringVar(
            value=self.settings.get("host", DEFAULT_HOST)
        )
        self.port_var = tk.StringVar(
            value=str(self.settings.get("port", DEFAULT_PORT))
        )
        self.ssh_host_var = tk.StringVar(
            value=self.settings.get("ssh_host", DEFAULT_SSH_HOST)
        )
        self.ssh_port_var = tk.StringVar(
            value=str(self.settings.get("ssh_port", DEFAULT_SSH_PORT))
        )
        self.ssh_user_var = tk.StringVar(
            value=self.settings.get("ssh_user", DEFAULT_SSH_USER)
        )
        self.ssh_command_var = tk.StringVar(
            value=(
                self.settings.get("ssh_command", DEFAULT_SSH_COMMAND)
                if IS_LINUX
                else ""
            )
        )
        self.remote_path_var = tk.StringVar(
            value=_normalise_remote_path(
                str(self.settings.get("remote_path", DEFAULT_REMOTE_PATH))
            )
        )
        self.command_var = tk.StringVar(
            value=self.settings.get("last_command", "sysinfo")
        )
        self.eggdrop_host_var = tk.StringVar(
            value=self.settings.get("eggdrop_host", DEFAULT_EGGDROP_HOST)
        )
        self.eggdrop_profile_var = tk.StringVar(
            value=_normalise_eggdrop_profile_name(
                str(self.settings.get("eggdrop_profile", "Direct"))
            )
        )
        self.eggdrop_port_var = tk.StringVar(
            value=str(self.settings.get("eggdrop_port", DEFAULT_EGGDROP_PORT))
        )
        self.eggdrop_handle_var = tk.StringVar(
            value=self.settings.get("eggdrop_handle", DEFAULT_EGGDROP_HANDLE)
        )
        self.eggdrop_ssh_host_var = tk.StringVar(
            value=self.settings.get(
                "eggdrop_ssh_host", DEFAULT_EGGDROP_SSH_HOST
            )
        )
        self.eggdrop_ssh_port_var = tk.StringVar(
            value=str(
                self.settings.get("eggdrop_ssh_port", DEFAULT_EGGDROP_SSH_PORT)
            )
        )
        self.eggdrop_ssh_user_var = tk.StringVar(
            value=self.settings.get(
                "eggdrop_ssh_user", DEFAULT_EGGDROP_SSH_USER
            )
        )
        self.eggdrop_remote_host_var = tk.StringVar(
            value=self.settings.get(
                "eggdrop_remote_host", DEFAULT_EGGDROP_REMOTE_HOST
            )
        )
        self.eggdrop_remote_port_var = tk.StringVar(
            value=str(
                self.settings.get(
                    "eggdrop_remote_port", DEFAULT_EGGDROP_REMOTE_PORT
                )
            )
        )
        self.eggdrop_password_var = tk.StringVar(value="")
        self.eggdrop_input_var = tk.StringVar(value="")
        self.eggdrop_status_var = tk.StringVar(value="Disconnected")
        self.eggdrop_login_state = "disconnected"
        self.status_var = tk.StringVar(value="Ready")
        self.theme_var = tk.StringVar(
            value=self.settings.get("theme", DEFAULT_THEME)
        )
        self.diagnostic_logging_var = tk.BooleanVar(
            value=_bool_setting(
                self.settings.get("diagnostic_logging_enabled")
            )
        )
        self.diagnostic_log_path_var = tk.StringVar(
            value=str(
                self.settings.get(
                    "diagnostic_log_path", DEFAULT_DIAGNOSTIC_LOG
                )
            )
        )
        self.theme_available = _apply_theme(self.theme_var.get())
        self.output_context_index = "1.0"
        self.settings_context_widget = None
        self.last_failed_diagnostic = ""
        self.eggdrop_socket: socket.socket | None = None
        self.eggdrop_connected = False
        self.eggdrop_lock = threading.Lock()
        self.eggdrop_pending_redactions: list[str] = []
        self.eggdrop_ssh_process: subprocess.Popen | None = None

        self._build()
        self._restore_window_geometry()
        self._poll_results()
        self._poll_eggdrop_events()
        self._start_status_probe()
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        self.root.title("LocalControl Test GUI")
        self.root.minsize(720, 420)

        outer = ttk.Frame(self.root, padding=12)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(outer)
        notebook.grid(row=0, column=0, sticky="nsew")
        local_tab = ttk.Frame(notebook, padding=12)
        eggdrops_tab = ttk.Frame(notebook, padding=12)
        settings_tab = ttk.Frame(notebook, padding=12)
        help_tab = ttk.Frame(notebook, padding=12)
        notebook.add(local_tab, text="Limnoria")
        notebook.add(eggdrops_tab, text="Eggdrop")
        notebook.add(settings_tab, text="Limnoria Settings")
        notebook.add(help_tab, text="Help")
        local_tab.columnconfigure(0, weight=1)
        local_tab.rowconfigure(2, weight=1)
        eggdrops_tab.columnconfigure(0, weight=1)
        eggdrops_tab.rowconfigure(3, weight=1)
        settings_tab.columnconfigure(0, weight=1)
        help_tab.columnconfigure(0, weight=1)
        help_tab.rowconfigure(0, weight=1)

        mode_row = ttk.Frame(local_tab)
        mode_row.grid(row=0, column=0, sticky="ew")
        mode_row.columnconfigure(3, weight=1)
        transport_column = 0
        if IS_LINUX:
            ttk.Radiobutton(
                mode_row,
                text="UNIX socket",
                variable=self.mode_var,
                value="socket",
                command=self._update_transport_state,
            ).grid(row=0, column=transport_column, sticky="w")
            transport_column += 1
        if IS_LINUX:
            ttk.Radiobutton(
                mode_row,
                text="TCP socket",
                variable=self.mode_var,
                value="tcp",
                command=self._update_transport_state,
            ).grid(row=0, column=transport_column, padx=(16, 0), sticky="w")
            transport_column += 1
        ttk.Radiobutton(
            mode_row,
            text="SSH",
            variable=self.mode_var,
            value="ssh",
            command=self._update_transport_state,
        ).grid(row=0, column=transport_column, padx=(16, 0), sticky="w")
        self.transport_status = ttk.Label(mode_row, text="")
        self.transport_status.grid(row=0, column=3, padx=(16, 0), sticky="w")

        socket_row = ttk.Frame(settings_tab)
        if IS_LINUX:
            socket_row.grid(row=0, column=0, sticky="ew")
        socket_row.columnconfigure(1, weight=1)
        self.socket_label = ttk.Label(socket_row, text="Socket")
        self.socket_label.grid(row=0, column=0, sticky="w")
        self.socket_entry = ttk.Entry(socket_row, textvariable=self.socket_var)
        self.socket_entry.grid(row=0, column=1, padx=(8, 0), sticky="ew")

        tcp_row = ttk.Frame(settings_tab)
        if IS_LINUX:
            tcp_row.grid(row=1, column=0, pady=(8, 0), sticky="ew")
        tcp_row.columnconfigure(1, weight=1)
        self.host_label = ttk.Label(tcp_row, text="Host")
        self.host_label.grid(row=0, column=0, sticky="w")
        self.host_entry = ttk.Entry(tcp_row, textvariable=self.host_var)
        self.host_entry.grid(row=0, column=1, padx=(8, 12), sticky="ew")
        self.port_label = ttk.Label(tcp_row, text="Port")
        self.port_label.grid(row=0, column=2, sticky="w")
        self.port_entry = ttk.Entry(
            tcp_row, textvariable=self.port_var, width=8
        )
        self.port_entry.grid(row=0, column=3, padx=(8, 0), sticky="w")

        ssh_row = ttk.Frame(settings_tab)
        ssh_row.grid(row=2, column=0, pady=(8, 0), sticky="ew")
        ssh_row.columnconfigure(3, weight=1)
        self.ssh_user_label = ttk.Label(ssh_row, text="User")
        self.ssh_user_label.grid(row=0, column=0, sticky="w")
        self.ssh_user_entry = ttk.Combobox(
            ssh_row,
            textvariable=self.ssh_user_var,
            values=self.ssh_user_history,
            width=14,
        )
        self.ssh_user_entry.grid(row=0, column=1, padx=(8, 12), sticky="w")
        self.ssh_host_label = ttk.Label(ssh_row, text="SSH host")
        self.ssh_host_label.grid(row=0, column=2, sticky="w")
        self.ssh_host_entry = ttk.Combobox(
            ssh_row,
            textvariable=self.ssh_host_var,
            values=self.ssh_host_history,
        )
        self.ssh_host_entry.grid(row=0, column=3, padx=(8, 12), sticky="ew")
        self.ssh_port_label = ttk.Label(ssh_row, text="Port")
        self.ssh_port_label.grid(row=0, column=4, sticky="w")
        self.ssh_port_entry = ttk.Entry(
            ssh_row, textvariable=self.ssh_port_var, width=8
        )
        self.ssh_port_entry.grid(row=0, column=5, padx=(8, 0), sticky="w")

        remote_row = ttk.Frame(settings_tab)
        remote_row.grid(row=3, column=0, pady=(8, 0), sticky="ew")
        remote_row.columnconfigure(1, weight=1)
        self.remote_path_label = ttk.Label(remote_row, text="Remote path")
        self.remote_path_label.grid(row=0, column=0, sticky="w")
        self.remote_path_entry = ttk.Entry(
            remote_row, textvariable=self.remote_path_var
        )
        self.remote_path_entry.grid(row=0, column=1, padx=(8, 0), sticky="ew")

        self.ssh_command_label = None
        self.ssh_command_entry = None
        theme_row_index = 4
        if IS_LINUX:
            ssh_command_row = ttk.Frame(settings_tab)
            ssh_command_row.grid(row=4, column=0, pady=(8, 0), sticky="ew")
            ssh_command_row.columnconfigure(1, weight=1)
            self.ssh_command_label = ttk.Label(
                ssh_command_row, text="SSH client"
            )
            self.ssh_command_label.grid(row=0, column=0, sticky="w")
            self.ssh_command_entry = ttk.Entry(
                ssh_command_row, textvariable=self.ssh_command_var
            )
            self.ssh_command_entry.grid(
                row=0, column=1, padx=(8, 0), sticky="ew"
            )
            theme_row_index = 5
        else:
            ssh_help = ttk.Label(
                settings_tab,
                text=(
                    "Windows OpenSSH needs a key or ssh-agent identity. Password "
                    "prompts are not available in the GUI."
                ),
                wraplength=680,
            )
            ssh_help.grid(row=4, column=0, pady=(8, 0), sticky="w")
            theme_row_index = 5

        diagnostics_row = ttk.Frame(settings_tab)
        diagnostics_row.grid(
            row=theme_row_index, column=0, pady=(12, 0), sticky="ew"
        )
        diagnostics_row.columnconfigure(2, weight=1)
        self.diagnostic_logging_check = ttk.Checkbutton(
            diagnostics_row,
            text="Enable diagnostics",
            variable=self.diagnostic_logging_var,
            command=self._save_settings,
        )
        self.diagnostic_logging_check.grid(row=0, column=0, sticky="w")
        ttk.Label(diagnostics_row, text="Log file").grid(
            row=0, column=1, padx=(16, 0), sticky="w"
        )
        self.diagnostic_log_path_entry = ttk.Entry(
            diagnostics_row, textvariable=self.diagnostic_log_path_var
        )
        self.diagnostic_log_path_entry.grid(
            row=0, column=2, padx=(8, 0), sticky="ew"
        )
        theme_row_index += 1

        for widget in (
            self.socket_entry,
            self.host_entry,
            self.port_entry,
            self.ssh_user_entry,
            self.ssh_host_entry,
            self.ssh_port_entry,
            self.remote_path_entry,
            self.ssh_command_entry,
            self.diagnostic_log_path_entry,
        ):
            if widget is not None:
                self._bind_settings_edit_menu(widget)

        theme_row = ttk.Frame(settings_tab)
        theme_row.grid(
            row=theme_row_index, column=0, pady=(12, 0), sticky="ew"
        )
        ttk.Label(theme_row, text="Theme").grid(row=0, column=0, sticky="w")
        self.theme_box = ttk.Combobox(
            theme_row,
            textvariable=self.theme_var,
            values=("dark", "light"),
            state="readonly",
            width=8,
        )
        self.theme_box.grid(row=0, column=1, padx=(8, 0), sticky="w")
        self.theme_box.bind("<<ComboboxSelected>>", self._change_theme)
        if not self.theme_available:
            self.theme_box.configure(state="disabled")

        command_row = ttk.Frame(local_tab)
        command_row.grid(row=1, column=0, pady=(12, 0), sticky="ew")
        command_row.columnconfigure(1, weight=1)
        ttk.Label(command_row, text="Command").grid(
            row=0, column=0, sticky="w"
        )
        self.command_entry = ttk.Combobox(
            command_row,
            textvariable=self.command_var,
            values=self.command_history,
        )
        self.command_entry.grid(row=0, column=1, padx=(8, 8), sticky="ew")
        self.command_entry.bind("<Return>", lambda _event: self._send())
        self._bind_context_menu(self.command_entry, self._show_command_menu)
        self._bind_command_shortcuts(self.command_entry)
        self.send_button = ttk.Button(
            command_row, text="Send", command=self._send
        )
        self.send_button.grid(row=0, column=2, sticky="e")
        self.probe_button = ttk.Button(
            command_row, text="Probe", command=lambda: self._send("sysinfo")
        )
        self.test_ssh_button = ttk.Button(
            command_row, text="Test SSH", command=self._test_ssh_connection
        )
        self.test_ssh_button.grid(row=0, column=3, padx=(8, 0), sticky="e")
        self.probe_button.grid(row=0, column=4, padx=(8, 0), sticky="e")

        output_frame = ttk.Frame(local_tab)
        output_frame.grid(row=2, column=0, pady=(12, 0), sticky="nsew")
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)

        text_font = _windows_mono_font(self.root)

        self.output = tk.Text(
            output_frame, wrap="word", height=12, font=text_font
        )
        self.output.grid(row=0, column=0, sticky="nsew")
        self._configure_output_tags()
        self._bind_context_menu(self.output, self._show_output_menu)
        self.output.bind("<Control-x>", self._cut_selected_output)
        self.output.bind("<Control-c>", self._copy_selected_output)
        self.output.bind("<Control-a>", self._select_output)
        self._bind_output_shortcuts()
        self.output.bind("<Delete>", self._delete_output_selection_or_block)
        self.output.bind("<KP_Delete>", self._delete_output_selection_or_block)
        self.output.bind(
            "<KP_Decimal>", self._delete_output_selection_or_block
        )
        self.output.bind("<KeyPress>", self._handle_output_keypress)
        for sequence in ("<Delete>", "<KP_Delete>", "<KP_Decimal>"):
            self.root.bind(sequence, self._handle_root_delete_key, add="+")
        scrollbar = ttk.Scrollbar(
            output_frame, orient="vertical", command=self.output.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.output.configure(yscrollcommand=scrollbar.set)
        self.output_menu = tk.Menu(self.root, tearoff=False)
        self.output_menu.add_command(
            label="Cut selected",
            command=self._cut_selected_output,
            accelerator=self._menu_shortcut("x"),
        )
        self.output_menu.add_command(
            label="Copy selected",
            command=self._copy_selected,
            accelerator=self._menu_shortcut("c"),
        )
        self.output_menu.add_command(
            label="Copy all", command=self._copy_output
        )
        self.output_menu.add_command(
            label="Copy command", command=self._copy_context_command
        )
        self.output_menu.add_command(
            label="Re-run command", command=self._rerun_context_command
        )
        self.output_menu.add_separator()
        self.output_menu.add_command(
            label="Clear output", command=self._clear_output
        )

        self.command_menu = tk.Menu(self.root, tearoff=False)
        self.command_menu.add_command(
            label="Cut",
            command=self._cut_command,
            accelerator=self._menu_shortcut("x"),
        )
        self.command_menu.add_command(
            label="Copy",
            command=self._copy_command,
            accelerator=self._menu_shortcut("c"),
        )
        self.command_menu.add_command(
            label="Paste",
            command=self._paste_command,
            accelerator=self._menu_shortcut("v"),
        )
        self.command_menu.add_separator()
        self.command_menu.add_command(
            label="Select all",
            command=self._select_command,
            accelerator=self._menu_shortcut("a"),
        )

        self.settings_menu = tk.Menu(self.root, tearoff=False)
        self.settings_menu.add_command(
            label="Cut",
            command=self._cut_settings_field,
            accelerator=self._menu_shortcut("x"),
        )
        self.settings_menu.add_command(
            label="Copy",
            command=self._copy_settings_field,
            accelerator=self._menu_shortcut("c"),
        )
        self.settings_menu.add_command(
            label="Paste",
            command=self._paste_settings_field,
            accelerator=self._menu_shortcut("v"),
        )
        self.settings_menu.add_separator()
        self.settings_menu.add_command(
            label="Select all",
            command=self._select_settings_field,
            accelerator=self._menu_shortcut("a"),
        )

        status_row = ttk.Frame(local_tab)
        status_row.grid(row=3, column=0, pady=(8, 0), sticky="ew")
        status_row.columnconfigure(0, weight=1)
        ttk.Label(status_row, textvariable=self.status_var).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(status_row, text="Clear", command=self._clear_output).grid(
            row=0, column=1, sticky="e"
        )
        ttk.Button(status_row, text="Copy", command=self._copy_output).grid(
            row=0, column=2, padx=(8, 0), sticky="e"
        )
        self.copy_diagnostics_button = ttk.Button(
            status_row,
            text="Copy diagnostics",
            command=self._copy_last_failed_diagnostic,
            state="disabled",
        )
        self.copy_diagnostics_button.grid(
            row=0, column=3, padx=(8, 0), sticky="e"
        )
        ttk.Button(status_row, text="Close", command=self._close).grid(
            row=0, column=4, padx=(8, 0), sticky="e"
        )

        self._build_eggdrops_tab(eggdrops_tab, text_font)
        self._build_help_tab(help_tab)
        self._update_transport_state()
        self.command_entry.focus_set()

    def _build_eggdrops_tab(self, parent: ttk.Frame, text_font) -> None:
        profile_row = ttk.Frame(parent)
        profile_row.grid(row=0, column=0, sticky="ew")
        profile_row.columnconfigure(1, weight=1)
        ttk.Label(profile_row, text="Transport").grid(
            row=0, column=0, sticky="w"
        )
        self.eggdrop_profile_combo = ttk.Combobox(
            profile_row,
            textvariable=self.eggdrop_profile_var,
            values=self.eggdrop_profile_names,
            state="readonly",
        )
        self.eggdrop_profile_combo.grid(
            row=0, column=1, padx=(8, 0), sticky="ew"
        )
        self.eggdrop_profile_combo.bind(
            "<<ComboboxSelected>>", self._select_eggdrop_profile
        )

        connection_row = ttk.Frame(parent)
        connection_row.grid(row=1, column=0, pady=(12, 0), sticky="ew")
        connection_row.columnconfigure(1, weight=1)
        connection_row.columnconfigure(3, weight=1)

        ttk.Label(connection_row, text="Host").grid(
            row=0, column=0, sticky="w"
        )
        self.eggdrop_host_entry = ttk.Entry(
            connection_row, textvariable=self.eggdrop_host_var
        )
        self.eggdrop_host_entry.grid(
            row=0, column=1, padx=(8, 12), sticky="ew"
        )
        ttk.Label(connection_row, text="Port").grid(
            row=0, column=2, sticky="w"
        )
        self.eggdrop_port_entry = ttk.Entry(
            connection_row, textvariable=self.eggdrop_port_var, width=8
        )
        self.eggdrop_port_entry.grid(row=0, column=3, padx=(8, 12), sticky="w")
        self.eggdrop_connect_button = ttk.Button(
            connection_row, text="Connect", command=self._eggdrop_connect
        )
        self.eggdrop_connect_button.grid(row=0, column=4, sticky="e")
        self.eggdrop_disconnect_button = ttk.Button(
            connection_row,
            text="Disconnect",
            command=self._eggdrop_disconnect,
            state="disabled",
        )
        self.eggdrop_disconnect_button.grid(
            row=0, column=5, padx=(8, 0), sticky="e"
        )

        tunnel_row = ttk.Frame(parent)
        tunnel_row.grid(row=2, column=0, pady=(12, 0), sticky="ew")
        tunnel_row.columnconfigure(1, weight=1)
        tunnel_row.columnconfigure(3, weight=1)
        tunnel_row.columnconfigure(7, weight=1)
        ttk.Label(tunnel_row, text="SSH user").grid(
            row=0, column=0, sticky="w"
        )
        self.eggdrop_ssh_user_entry = ttk.Combobox(
            tunnel_row,
            textvariable=self.eggdrop_ssh_user_var,
            values=self.eggdrop_ssh_user_history,
        )
        self.eggdrop_ssh_user_entry.grid(
            row=0, column=1, padx=(8, 12), sticky="ew"
        )
        ttk.Label(tunnel_row, text="SSH host").grid(
            row=0, column=2, sticky="w"
        )
        self.eggdrop_ssh_host_entry = ttk.Combobox(
            tunnel_row,
            textvariable=self.eggdrop_ssh_host_var,
            values=self.eggdrop_ssh_host_history,
        )
        self.eggdrop_ssh_host_entry.grid(
            row=0, column=3, padx=(8, 12), sticky="ew"
        )
        ttk.Label(tunnel_row, text="SSH port").grid(
            row=0, column=4, sticky="w"
        )
        self.eggdrop_ssh_port_entry = ttk.Entry(
            tunnel_row, textvariable=self.eggdrop_ssh_port_var, width=6
        )
        self.eggdrop_ssh_port_entry.grid(
            row=0, column=5, padx=(8, 12), sticky="w"
        )
        ttk.Label(tunnel_row, text="Remote Telnet").grid(
            row=0, column=6, sticky="w"
        )
        self.eggdrop_remote_host_entry = ttk.Entry(
            tunnel_row, textvariable=self.eggdrop_remote_host_var
        )
        self.eggdrop_remote_host_entry.grid(
            row=0, column=7, padx=(8, 8), sticky="ew"
        )
        self.eggdrop_remote_port_entry = ttk.Combobox(
            tunnel_row,
            textvariable=self.eggdrop_remote_port_var,
            values=self.eggdrop_remote_port_history,
            width=8,
        )
        self.eggdrop_remote_port_entry.grid(row=0, column=8, sticky="w")

        login_row = ttk.Frame(parent)
        login_row.grid(row=3, column=0, pady=(12, 0), sticky="ew")
        login_row.columnconfigure(1, weight=1)
        login_row.columnconfigure(3, weight=1)
        ttk.Label(login_row, text="Handle").grid(row=0, column=0, sticky="w")
        self.eggdrop_handle_entry = ttk.Entry(
            login_row, textvariable=self.eggdrop_handle_var
        )
        self.eggdrop_handle_entry.grid(
            row=0, column=1, padx=(8, 12), sticky="ew"
        )
        self.eggdrop_handle_entry.bind(
            "<Return>", lambda _event: self._eggdrop_send_handle()
        )
        ttk.Label(login_row, text="Password").grid(row=0, column=2, sticky="w")
        self.eggdrop_password_entry = ttk.Entry(
            login_row, textvariable=self.eggdrop_password_var, show="*"
        )
        self.eggdrop_password_entry.grid(
            row=0, column=3, padx=(8, 12), sticky="ew"
        )
        self.eggdrop_password_entry.bind(
            "<Return>", lambda _event: self._eggdrop_send_password()
        )
        self.eggdrop_handle_button = ttk.Button(
            login_row,
            text="Send handle",
            command=self._eggdrop_send_handle,
            state="disabled",
        )
        self.eggdrop_handle_button.grid(row=0, column=4, sticky="e")
        self.eggdrop_password_button = ttk.Button(
            login_row,
            text="Send password",
            command=self._eggdrop_send_password,
            state="disabled",
        )
        self.eggdrop_password_button.grid(
            row=0, column=5, padx=(8, 0), sticky="e"
        )

        transcript_frame = ttk.Frame(parent)
        transcript_frame.grid(row=4, column=0, pady=(12, 0), sticky="nsew")
        transcript_frame.columnconfigure(0, weight=1)
        transcript_frame.rowconfigure(0, weight=1)
        self.eggdrop_output = tk.Text(
            transcript_frame, wrap="word", height=12, font=text_font
        )
        self.eggdrop_output.grid(row=0, column=0, sticky="nsew")
        self._configure_eggdrop_output_tags()
        self._bind_context_menu(
            self.eggdrop_output, self._show_eggdrop_output_menu
        )
        eggdrop_scrollbar = ttk.Scrollbar(
            transcript_frame,
            orient="vertical",
            command=self.eggdrop_output.yview,
        )
        eggdrop_scrollbar.grid(row=0, column=1, sticky="ns")
        self.eggdrop_output.configure(yscrollcommand=eggdrop_scrollbar.set)

        input_row = ttk.Frame(parent)
        input_row.grid(row=5, column=0, pady=(8, 0), sticky="ew")
        input_row.columnconfigure(1, weight=1)
        ttk.Label(input_row, text="Input").grid(row=0, column=0, sticky="w")
        self.eggdrop_input_entry = ttk.Entry(
            input_row, textvariable=self.eggdrop_input_var, state="disabled"
        )
        self.eggdrop_input_entry.grid(
            row=0, column=1, padx=(8, 8), sticky="ew"
        )
        self.eggdrop_input_entry.bind(
            "<Return>", lambda _event: self._eggdrop_send()
        )
        self.eggdrop_input_entry.bind("<Up>", self._eggdrop_history_previous)
        self.eggdrop_input_entry.bind("<Down>", self._eggdrop_history_next)
        self.eggdrop_send_button = ttk.Button(
            input_row,
            text="Send",
            command=self._eggdrop_send,
            state="disabled",
        )
        self.eggdrop_send_button.grid(row=0, column=2, sticky="e")
        ttk.Button(
            input_row, text="Clear", command=self._clear_eggdrop_output
        ).grid(row=0, column=3, padx=(8, 0), sticky="e")
        ttk.Button(
            input_row, text="Copy", command=self._copy_eggdrop_output
        ).grid(row=0, column=4, padx=(8, 0), sticky="e")

        status_row = ttk.Frame(parent)
        status_row.grid(row=6, column=0, pady=(8, 0), sticky="ew")
        status_row.columnconfigure(0, weight=1)
        ttk.Label(status_row, textvariable=self.eggdrop_status_var).grid(
            row=0, column=0, sticky="w"
        )

        self.eggdrop_output_menu = tk.Menu(self.root, tearoff=False)
        self.eggdrop_output_menu.add_command(
            label="Copy selected", command=self._copy_selected_eggdrop_output
        )
        self.eggdrop_output_menu.add_command(
            label="Copy all", command=self._copy_eggdrop_output
        )
        self.eggdrop_output_menu.add_command(
            label="Clear output", command=self._clear_eggdrop_output
        )
        self._apply_selected_eggdrop_profile()

        for widget in (
            self.eggdrop_host_entry,
            self.eggdrop_port_entry,
            self.eggdrop_ssh_user_entry,
            self.eggdrop_ssh_host_entry,
            self.eggdrop_ssh_port_entry,
            self.eggdrop_remote_host_entry,
            self.eggdrop_remote_port_entry,
            self.eggdrop_handle_entry,
            self.eggdrop_password_entry,
            self.eggdrop_input_entry,
        ):
            self._bind_settings_edit_menu(widget)

    def _build_help_tab(self, parent: ttk.Frame) -> None:
        help_frame = ttk.Frame(parent)
        help_frame.grid(row=0, column=0, sticky="nsew")
        help_frame.columnconfigure(0, weight=1)
        help_frame.rowconfigure(0, weight=1)

        help_text = tk.Text(
            help_frame,
            wrap="word",
            height=18,
            font=_windows_mono_font(self.root),
        )
        help_text.grid(row=0, column=0, sticky="nsew")
        help_scrollbar = ttk.Scrollbar(
            help_frame, orient="vertical", command=help_text.yview
        )
        help_scrollbar.grid(row=0, column=1, sticky="ns")
        help_text.configure(yscrollcommand=help_scrollbar.set)
        help_text.insert("1.0", _help_text())
        help_text.configure(state="disabled")

    def _bind_context_menu(self, widget, callback) -> None:
        widget.bind("<Button-3>", callback)
        widget.bind("<Button-2>", callback)

    def _bind_command_shortcuts(self, widget) -> None:
        widget.bind("<Control-x>", self._cut_command)
        widget.bind("<Control-c>", self._copy_command)
        widget.bind("<Control-v>", self._paste_command)
        widget.bind("<Control-a>", self._select_command)

    def _bind_settings_edit_menu(self, widget) -> None:
        self._bind_context_menu(widget, self._show_settings_menu)
        widget.bind("<Control-x>", self._cut_settings_field)
        widget.bind("<Control-c>", self._copy_settings_field)
        widget.bind("<Control-v>", self._paste_settings_field)
        widget.bind("<Control-a>", self._select_settings_field)
        widget.bind("<KP_Delete>", self._delete_settings_field)
        widget.bind("<KP_Decimal>", self._delete_settings_field)
        widget.bind("<KeyPress>", self._handle_settings_keypress)

    def _bind_output_shortcuts(self) -> None:
        return

    def _menu_shortcut(self, key: str) -> str:
        return f"Ctrl+{key.upper()}"

    def _start_status_probe(self) -> None:
        self.status_var.set("Checking LocalControl status...")
        probe_request = self._probe_request()
        thread = threading.Thread(
            target=self._probe_status,
            args=(probe_request,),
            daemon=True,
        )
        thread.start()

    def _probe_request(self) -> dict[str, object]:
        return {
            "mode": self.mode_var.get(),
            "socket_path": self.socket_var.get().strip(),
            "host": self.host_var.get().strip(),
            "port": self.port_var.get().strip(),
            "ssh_enabled": self.mode_var.get() == "ssh",
            "ssh_host": self.ssh_host_var.get().strip(),
            "ssh_port": self.ssh_port_var.get().strip(),
            "ssh_user": self.ssh_user_var.get().strip(),
            "ssh_command": self._ssh_command(),
            "remote_path": _normalise_remote_path(
                self.remote_path_var.get().strip()
            ),
        }

    def _probe_status(self, probe_request: dict[str, object]) -> None:
        active_mode = str(probe_request["mode"])
        socket_path = str(probe_request["socket_path"])
        socket_exists = bool(socket_path and os.path.exists(socket_path))
        unix_ok = False
        tcp_ok = False
        ssh_ok = None
        unix_checked = active_mode == "socket"
        tcp_checked = active_mode == "tcp"
        details = []

        if unix_checked and socket_exists:
            try:
                send_socket_command(socket_path, PROBE_COMMAND)
            except Exception as exc:
                details.append("UNIX error: %s" % exc)
            else:
                unix_ok = True
        elif unix_checked:
            details.append("UNIX socket missing")

        if tcp_checked:
            try:
                host = str(probe_request["host"])
                port = int(str(probe_request["port"]))
                send_tcp_command(host, port, PROBE_COMMAND)
            except Exception as exc:
                details.append("TCP error: %s" % exc)
            else:
                tcp_ok = True

        if probe_request["ssh_enabled"] and probe_request["ssh_host"]:
            ssh_ok = False
            try:
                test_ssh_connection(
                    str(probe_request["ssh_host"]),
                    int(str(probe_request["ssh_port"])),
                    str(probe_request["ssh_user"]),
                    str(probe_request["ssh_command"]),
                    str(probe_request["remote_path"]),
                )
            except Exception as exc:
                details.append("SSH error: %s" % exc)
            else:
                ssh_ok = True

        self.results.put(
            (
                unix_ok or tcp_ok or bool(ssh_ok),
                "status probe",
                _format_status_probe(
                    active_mode,
                    socket_exists,
                    unix_checked,
                    unix_ok,
                    tcp_checked,
                    tcp_ok,
                    ssh_ok,
                    details,
                    include_unix=IS_LINUX,
                    include_tcp=IS_LINUX,
                ),
                "",
            )
        )

    def _update_transport_state(self) -> None:
        mode = self.mode_var.get()
        if not IS_LINUX and mode != "ssh":
            self.mode_var.set("ssh")
            mode = "ssh"
        using_socket = mode == "socket"
        using_tcp = mode == "tcp"
        using_ssh = mode == "ssh"
        socket_state = "normal" if using_socket else "disabled"
        tcp_state = "normal" if using_tcp else "disabled"
        ssh_state = "normal" if using_ssh else "disabled"
        active_transport = {
            "socket": "UNIX socket active",
            "tcp": "TCP socket active",
            "ssh": "SSH active",
        }.get(mode, "SSH active" if not IS_LINUX else "UNIX socket active")
        self.transport_status.configure(text=active_transport)
        self.socket_label.configure(state=socket_state)
        self.socket_entry.configure(state=socket_state)
        self.host_label.configure(state=tcp_state)
        self.host_entry.configure(state=tcp_state)
        self.port_label.configure(state=tcp_state)
        self.port_entry.configure(state=tcp_state)
        self.ssh_user_label.configure(state=ssh_state)
        self.ssh_user_entry.configure(state=ssh_state)
        self.ssh_host_label.configure(state=ssh_state)
        self.ssh_host_entry.configure(state=ssh_state)
        self.ssh_port_label.configure(state=ssh_state)
        self.ssh_port_entry.configure(state=ssh_state)
        self.remote_path_label.configure(state=ssh_state)
        self.remote_path_entry.configure(state=ssh_state)
        if (
            self.ssh_command_label is not None
            and self.ssh_command_entry is not None
        ):
            self.ssh_command_label.configure(state=ssh_state)
            self.ssh_command_entry.configure(state=ssh_state)
        self.test_ssh_button.configure(state=ssh_state)

    def _change_theme(self, _event: tk.Event) -> None:
        if _apply_theme(self.theme_var.get()):
            self._configure_output_tags()
            self._configure_eggdrop_output_tags()
            self.status_var.set("Theme changed")
            self._save_settings()

    def _send(self, command_override: str | None = None) -> None:
        command = (command_override or self.command_var.get()).strip()
        if not command:
            self._append_output("No command entered.\n")
            return
        if command_override is not None:
            self.command_var.set(command)

        try:
            mode, endpoint = self._transport_details()
        except ValueError as exc:
            self._append_output(f"Error:\n{exc}\n\n")
            return
        transport_request = self._transport_request(mode, command)
        transport_request["endpoint"] = endpoint
        transport_request["diagnostic_logging_enabled"] = (
            self.diagnostic_logging_var.get()
        )
        transport_request["diagnostic_log_path"] = (
            self.diagnostic_log_path_var.get().strip()
        )

        self._set_busy(True)
        self.status_var.set(f"Sending to {endpoint}...")
        self._record_history(command)
        self._save_settings()
        thread = threading.Thread(
            target=self._send_in_background,
            args=(transport_request,),
            daemon=True,
        )
        thread.start()

    def _test_ssh_connection(self) -> None:
        if self.mode_var.get() != "ssh":
            self._append_output("Error:\nSSH mode is required.\n\n")
            return
        try:
            mode, endpoint = self._transport_details()
        except ValueError as exc:
            self._append_output(f"Error:\n{exc}\n\n")
            return
        if mode != "ssh":
            self._append_output("Error:\nSSH mode is required.\n\n")
            return

        transport_request = self._transport_request(
            mode, "SSH connection test"
        )
        transport_request["endpoint"] = endpoint
        transport_request["diagnostic_logging_enabled"] = (
            self.diagnostic_logging_var.get()
        )
        transport_request["diagnostic_log_path"] = (
            self.diagnostic_log_path_var.get().strip()
        )

        self._set_busy(True)
        self.status_var.set(f"Testing SSH to {endpoint}...")
        self._save_settings()
        thread = threading.Thread(
            target=self._test_ssh_in_background,
            args=(transport_request,),
            daemon=True,
        )
        thread.start()

    def _test_ssh_in_background(
        self, transport_request: dict[str, object]
    ) -> None:
        endpoint = str(transport_request.get("endpoint", "ssh"))
        command = str(transport_request["command"])
        started = time.monotonic()
        try:
            reply = test_ssh_connection(
                str(transport_request["host"]),
                int(transport_request["port"]),
                str(transport_request["username"]),
                str(transport_request["ssh_command"]),
                str(transport_request["remote_path"]),
            )
        except Exception as exc:  # pragma: no cover - GUI error display.
            diagnostic = self._write_diagnostic(
                transport_request,
                endpoint,
                command,
                False,
                started,
                exc.__class__.__name__,
                str(exc),
            )
            self.results.put(
                (
                    False,
                    command,
                    str(exc),
                    _format_diagnostic_copy(diagnostic),
                )
            )
        else:
            self._write_diagnostic(
                transport_request, endpoint, command, True, started, "", ""
            )
            self.results.put((True, command, reply, ""))

    def _transport_details(self) -> tuple[str, str]:
        mode = self.mode_var.get()
        if mode == "telnet":
            self.mode_var.set("tcp")
            mode = "tcp"
        if not IS_LINUX and mode != "ssh":
            self.mode_var.set("ssh")
            mode = "ssh"

        if mode == "tcp":
            host = self.host_var.get().strip()
            if not host:
                raise ValueError("Host is required.")
            try:
                port = int(self.port_var.get())
            except ValueError as exc:
                raise ValueError("Port must be a number.") from exc
            if port < 1 or port > 65535:
                raise ValueError("Port must be between 1 and 65535.")
            return mode, f"{host}:{port}"

        if mode == "ssh":
            host = self.ssh_host_var.get().strip()
            user = self.ssh_user_var.get().strip()
            ssh_command = self._ssh_command()
            remote_path = self.remote_path_var.get().strip()
            if not host:
                raise ValueError("SSH host is required.")
            if not user:
                raise ValueError("SSH user is required.")
            if not remote_path:
                raise ValueError("Remote path is required.")
            try:
                port = int(self.ssh_port_var.get())
            except ValueError as exc:
                raise ValueError("SSH port must be a number.") from exc
            if port < 1 or port > 65535:
                raise ValueError("SSH port must be between 1 and 65535.")
            return (
                mode,
                f"{user}@{host}:{port} via {_ssh_command_label(ssh_command)}",
            )

        socket_path = self.socket_var.get().strip()
        if not socket_path:
            raise ValueError("Socket path is required.")
        return mode, socket_path

    def _transport_request(self, mode: str, command: str) -> dict[str, object]:
        request: dict[str, object] = {"mode": mode, "command": command}
        if mode == "tcp":
            request["host"] = self.host_var.get().strip()
            request["port"] = int(self.port_var.get())
        elif mode == "ssh":
            request["host"] = self.ssh_host_var.get().strip()
            request["port"] = int(self.ssh_port_var.get())
            request["username"] = self.ssh_user_var.get().strip()
            request["ssh_command"] = self._ssh_command()
            request["remote_path"] = self.remote_path_var.get().strip()
        else:
            request["socket_path"] = self.socket_var.get().strip()
        return request

    def _send_in_background(
        self, transport_request: dict[str, object]
    ) -> None:
        mode = str(transport_request["mode"])
        command = str(transport_request["command"])
        endpoint = str(transport_request.get("endpoint", mode))
        started = time.monotonic()
        try:
            if mode == "tcp":
                reply = send_tcp_command(
                    str(transport_request["host"]),
                    int(transport_request["port"]),
                    command,
                )
            elif mode == "ssh":
                reply = send_ssh_command(
                    str(transport_request["host"]),
                    int(transport_request["port"]),
                    str(transport_request["username"]),
                    str(transport_request["ssh_command"]),
                    str(transport_request["remote_path"]),
                    command,
                )
            else:
                reply = send_socket_command(
                    str(transport_request["socket_path"]), command
                )
        except Exception as exc:  # pragma: no cover - GUI error display.
            message = str(exc)
            if mode == "ssh":
                configured_path = str(transport_request["remote_path"])
                normalised_path = _normalise_remote_path(configured_path)
                effective_path = _quote_remote_path(configured_path)
                message = (
                    f"{message}\n\n"
                    "SSH remote path:\n"
                    f"Configured: {configured_path or '(empty)'}\n"
                    f"Normalised: {normalised_path or '(empty)'}\n"
                    f"Effective remote cd: {effective_path}"
                )
            diagnostic = self._write_diagnostic(
                transport_request,
                endpoint,
                command,
                False,
                started,
                exc.__class__.__name__,
                str(exc),
            )
            self.results.put(
                (False, command, message, _format_diagnostic_copy(diagnostic))
            )
        else:
            self._write_diagnostic(
                transport_request, endpoint, command, True, started, "", ""
            )
            self.results.put((True, command, reply, ""))

    def _write_diagnostic(
        self,
        transport_request: dict[str, object],
        endpoint: str,
        command: str,
        ok: bool,
        started: float,
        error_class: str,
        error_message: str,
    ) -> dict[str, object]:
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "transport": str(transport_request["mode"]),
            "endpoint": endpoint,
            "command": _command_summary(command),
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "ok": ok,
        }
        if not ok:
            entry["error_class"] = error_class
            entry["error_message"] = _short_error(error_message)
        if transport_request.get("diagnostic_logging_enabled"):
            log_path = str(
                transport_request.get("diagnostic_log_path", "")
            ).strip()
            if log_path:
                _append_diagnostic_log(Path(log_path), entry)
        return entry

    def _poll_results(self) -> None:
        try:
            result = self.results.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_results)
            return
        if len(result) == 3:
            ok, command, message = result
            diagnostic = ""
        else:
            ok, command, message, diagnostic = result

        try:
            prefix = "Reply" if ok else "Error"
            timestamp = datetime.now().strftime("%H:%M:%S")
            self._append_command_output(
                timestamp, command, prefix, message, ok
            )
            if not ok and diagnostic:
                self._set_last_failed_diagnostic(diagnostic)
            self.status_var.set("Ready")
        except tk.TclError as exc:
            self.status_var.set(f"Display error: {exc}")
        finally:
            self._set_busy(False)
            self.root.after(100, self._poll_results)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.send_button.configure(state=state)
        self.probe_button.configure(state=state)
        self.test_ssh_button.configure(
            state=(
                "disabled"
                if busy or self.mode_var.get() != "ssh"
                else "normal"
            )
        )

    def _eggdrop_connect(self) -> None:
        if self.eggdrop_connected:
            return
        profile = _eggdrop_profile_by_name(self.eggdrop_profile_var.get())
        if profile is None:
            self._append_eggdrop_output(
                "Eggdrop transport is invalid.\n", "eggdrop_error"
            )
            return
        host = self.eggdrop_host_var.get().strip()
        if not host:
            self._append_eggdrop_output(
                "Telnet host is required.\n", "eggdrop_error"
            )
            return
        try:
            port = int(self.eggdrop_port_var.get())
        except ValueError:
            self._append_eggdrop_output(
                "Port must be a number.\n", "eggdrop_error"
            )
            return
        if port < 1 or port > 65535:
            self._append_eggdrop_output(
                "Port must be between 1 and 65535.\n", "eggdrop_error"
            )
            return
        profile = dict(profile)
        profile["port"] = port
        if profile.get("ssh_tunnel"):
            ssh_user = self.eggdrop_ssh_user_var.get().strip()
            ssh_host = self.eggdrop_ssh_host_var.get().strip()
            remote_host = self.eggdrop_remote_host_var.get().strip()
            if not ssh_user:
                self._append_eggdrop_output(
                    "SSH user is required.\n", "eggdrop_error"
                )
                return
            if not ssh_host:
                self._append_eggdrop_output(
                    "SSH host is required.\n", "eggdrop_error"
                )
                return
            if not remote_host:
                self._append_eggdrop_output(
                    "Remote Telnet host is required.\n", "eggdrop_error"
                )
                return
            try:
                ssh_port = int(self.eggdrop_ssh_port_var.get())
                remote_port = int(self.eggdrop_remote_port_var.get())
            except ValueError:
                self._append_eggdrop_output(
                    "SSH and remote Telnet ports must be numbers.\n",
                    "eggdrop_error",
                )
                return
            if ssh_port < 1 or ssh_port > 65535:
                self._append_eggdrop_output(
                    "SSH port must be between 1 and 65535.\n",
                    "eggdrop_error",
                )
                return
            if remote_port < 1 or remote_port > 65535:
                self._append_eggdrop_output(
                    "Remote Telnet port must be between 1 and 65535.\n",
                    "eggdrop_error",
                )
                return
            profile.update(
                {
                    "ssh_user": ssh_user,
                    "ssh_host": ssh_host,
                    "ssh_port": ssh_port,
                    "remote_host": remote_host,
                    "remote_port": remote_port,
                }
            )

        self.eggdrop_pending_redactions.clear()
        self._set_eggdrop_connected(False, connecting=True)
        self.eggdrop_status_var.set(f"Connecting to {host}:{port}...")
        self._save_settings()
        diagnostic = {
            "enabled": self.diagnostic_logging_var.get(),
            "path": self.diagnostic_log_path_var.get().strip(),
        }
        thread = threading.Thread(
            target=self._eggdrop_connect_in_background,
            args=(host, port, profile, diagnostic),
            daemon=True,
        )
        thread.start()

    def _select_eggdrop_profile(self, _event: tk.Event | None = None) -> None:
        if self.eggdrop_connected:
            return
        self._apply_selected_eggdrop_profile()
        self._save_settings()

    def _apply_selected_eggdrop_profile(self) -> None:
        profile = _eggdrop_profile_by_name(self.eggdrop_profile_var.get())
        if profile is None:
            self.eggdrop_profile_var.set("Direct")
            profile = _eggdrop_profile_by_name("Direct")
        if profile is None:
            return
        self._update_eggdrop_tunnel_state()

    def _update_eggdrop_tunnel_state(self) -> None:
        profile = _eggdrop_profile_by_name(self.eggdrop_profile_var.get())
        enabled = bool(profile and profile.get("ssh_tunnel"))
        state = (
            "normal" if enabled and not self.eggdrop_connected else "disabled"
        )
        for widget in (
            self.eggdrop_ssh_user_entry,
            self.eggdrop_ssh_host_entry,
            self.eggdrop_ssh_port_entry,
            self.eggdrop_remote_host_entry,
            self.eggdrop_remote_port_entry,
        ):
            widget.configure(state=state)

    def _eggdrop_connect_in_background(
        self,
        host: str,
        port: int,
        profile: dict[str, object],
        diagnostic: dict[str, object],
    ) -> None:
        tunnel_process = None
        try:
            if profile.get("ssh_tunnel"):
                self.eggdrop_events.put(("status", "Starting SSH tunnel..."))
                tunnel_process = start_eggdrop_ssh_tunnel(profile)
                with self.eggdrop_lock:
                    self.eggdrop_ssh_process = tunnel_process
                _write_eggdrop_diagnostic_entry(
                    diagnostic, f"{host}:{port}", "tunnel-start", True, ""
                )
                self.eggdrop_events.put(("status", "SSH tunnel active"))
            client = connect_eggdrop_endpoint(host, port, tunnel_process)
            client.settimeout(1.0)
        except Exception as exc:  # pragma: no cover - GUI error display.
            if tunnel_process is not None:
                _terminate_process(tunnel_process)
            with self.eggdrop_lock:
                if self.eggdrop_ssh_process is tunnel_process:
                    self.eggdrop_ssh_process = None
            if profile.get("ssh_tunnel"):
                _write_eggdrop_diagnostic_entry(
                    diagnostic,
                    f"{host}:{port}",
                    "tunnel-connect",
                    False,
                    str(exc),
                )
            self.eggdrop_events.put(("error", f"Connection failed: {exc}"))
            self.eggdrop_events.put(("disconnected", "Disconnected"))
            return

        with self.eggdrop_lock:
            self.eggdrop_socket = client
            self.eggdrop_connected = True
        self.eggdrop_events.put(("connected", f"Connected to {host}:{port}"))
        self._eggdrop_read_loop(client)

    def _eggdrop_read_loop(self, client: socket.socket) -> None:
        try:
            while True:
                try:
                    chunk = client.recv(EGGDROP_READ_BYTES)
                except socket.timeout:
                    with self.eggdrop_lock:
                        if (
                            not self.eggdrop_connected
                            or self.eggdrop_socket is not client
                        ):
                            break
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                self.eggdrop_events.put(("data", _decode_eggdrop_bytes(chunk)))
        finally:
            with self.eggdrop_lock:
                if self.eggdrop_socket is client:
                    self.eggdrop_socket = None
                    self.eggdrop_connected = False
            try:
                client.close()
            except OSError:
                pass
            self._close_eggdrop_tunnel()
            self.eggdrop_events.put(("disconnected", "Disconnected"))

    def _eggdrop_disconnect(self) -> None:
        self._close_eggdrop_socket()

    def _close_eggdrop_socket(self) -> None:
        with self.eggdrop_lock:
            client = self.eggdrop_socket
            self.eggdrop_socket = None
            self.eggdrop_connected = False
        if client is None:
            return
        try:
            client.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            client.close()
        except OSError:
            pass

    def _close_eggdrop_tunnel(self) -> None:
        with self.eggdrop_lock:
            process = self.eggdrop_ssh_process
            self.eggdrop_ssh_process = None
        if process is not None:
            _terminate_process(process)

    def _eggdrop_send_handle(self) -> None:
        handle = self.eggdrop_handle_var.get().strip()
        if not handle:
            self._append_eggdrop_output(
                "Handle is required.\n", "eggdrop_error"
            )
            return
        self._eggdrop_send_line(handle, "handle")

    def _eggdrop_send_password(self) -> None:
        password = self.eggdrop_password_var.get()
        if not password:
            self._append_eggdrop_output(
                "Password is required.\n", "eggdrop_error"
            )
            return
        if self._eggdrop_send_line(password, "password", redacted=True):
            self._add_eggdrop_redaction(password)
            self.eggdrop_password_var.set("")

    def _eggdrop_send(self) -> None:
        line = self.eggdrop_input_var.get()
        if not line.strip():
            return
        if self._eggdrop_send_line(line, "input"):
            self._record_eggdrop_input_history(line)
            self.eggdrop_input_var.set("")
            self.eggdrop_history_index = None
            self._save_settings()

    def _eggdrop_send_line(
        self, line: str, label: str, redacted: bool = False
    ) -> bool:
        with self.eggdrop_lock:
            client = self.eggdrop_socket
            connected = self.eggdrop_connected
        if client is None or not connected:
            self._append_eggdrop_output(
                "Eggdrop is not connected.\n", "eggdrop_error"
            )
            return False
        try:
            client.sendall((line + "\n").encode("utf-8"))
        except OSError as exc:
            self._append_eggdrop_output(
                f"Send failed: {exc}\n", "eggdrop_error"
            )
            self._close_eggdrop_socket()
            return False
        visible_line = "[redacted]" if redacted else line
        self._append_eggdrop_output(f"> {visible_line}\n", "eggdrop_input")
        self._write_eggdrop_diagnostic(
            self.eggdrop_host_var.get().strip(),
            _port_or_default(
                self.eggdrop_port_var.get(), DEFAULT_EGGDROP_PORT
            ),
            label,
            True,
            "",
        )
        return True

    def _poll_eggdrop_events(self) -> None:
        try:
            event, message = self.eggdrop_events.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_eggdrop_events)
            return

        if event == "connected":
            self._set_eggdrop_connected(True)
            self.eggdrop_login_state = "connected"
            self.eggdrop_status_var.set(message)
            self._append_eggdrop_output(f"{message}\n", "eggdrop_status")
            self._write_eggdrop_diagnostic(
                self.eggdrop_host_var.get().strip(),
                _port_or_default(
                    self.eggdrop_port_var.get(), DEFAULT_EGGDROP_PORT
                ),
                "connect",
                True,
                "",
            )
        elif event == "disconnected":
            self._set_eggdrop_connected(False)
            self.eggdrop_login_state = "disconnected"
            self.eggdrop_pending_redactions.clear()
            self.eggdrop_status_var.set(message)
            self._append_eggdrop_output(f"{message}\n", "eggdrop_status")
        elif event == "error":
            self._set_eggdrop_connected(False)
            self.eggdrop_login_state = "disconnected"
            self.eggdrop_status_var.set("Disconnected")
            self._append_eggdrop_output(f"{message}\n", "eggdrop_error")
            self._write_eggdrop_diagnostic(
                self.eggdrop_host_var.get().strip(),
                _port_or_default(
                    self.eggdrop_port_var.get(), DEFAULT_EGGDROP_PORT
                ),
                "connect",
                False,
                message,
            )
        elif event == "status":
            self.eggdrop_status_var.set(message)
            self._append_eggdrop_output(f"{message}\n", "eggdrop_status")
        else:
            redacted = self._redact_eggdrop_transcript(message)
            self._append_eggdrop_output(redacted, "eggdrop_data")
            self._handle_eggdrop_prompt(redacted)
        self.root.after(100, self._poll_eggdrop_events)

    def _handle_eggdrop_prompt(self, text: str) -> None:
        lowered = text.lower()
        if "please enter your handle" in lowered:
            self.eggdrop_login_state = "handle"
            self.eggdrop_status_var.set("Enter Eggdrop handle")
            self.eggdrop_handle_entry.focus_set()
            self.eggdrop_handle_entry.selection_range(0, "end")
            return
        if "enter your password" in lowered:
            self.eggdrop_login_state = "password"
            self.eggdrop_status_var.set("Enter Eggdrop password")
            self.eggdrop_password_entry.focus_set()
            return
        if (
            "connected to pudding" in lowered
            or "joined the party line" in lowered
        ):
            self.eggdrop_login_state = "partyline"
            self.eggdrop_status_var.set("Connected to Eggdrop partyline")
            self.eggdrop_input_entry.focus_set()

    def _add_eggdrop_redaction(self, secret: str) -> None:
        secret = secret.strip()
        if not secret:
            return
        if secret not in self.eggdrop_pending_redactions:
            self.eggdrop_pending_redactions.append(secret)

    def _redact_eggdrop_transcript(self, text: str) -> str:
        for secret in list(self.eggdrop_pending_redactions):
            if secret not in text:
                continue
            text = text.replace(secret, "[redacted]")
            self.eggdrop_pending_redactions.remove(secret)
        return text

    def _set_eggdrop_connected(
        self, connected: bool, connecting: bool = False
    ) -> None:
        if connecting:
            self.eggdrop_profile_combo.configure(state="disabled")
            self.eggdrop_connect_button.configure(state="disabled")
            self.eggdrop_disconnect_button.configure(state="disabled")
            self.eggdrop_handle_button.configure(state="disabled")
            self.eggdrop_password_button.configure(state="disabled")
            self.eggdrop_send_button.configure(state="disabled")
            self.eggdrop_input_entry.configure(state="disabled")
            for widget in (
                self.eggdrop_ssh_user_entry,
                self.eggdrop_ssh_host_entry,
                self.eggdrop_ssh_port_entry,
                self.eggdrop_remote_host_entry,
                self.eggdrop_remote_port_entry,
            ):
                widget.configure(state="disabled")
            return
        connected_state = "normal" if connected else "disabled"
        disconnected_state = "disabled" if connected else "normal"
        self.eggdrop_profile_combo.configure(
            state="disabled" if connected else "readonly"
        )
        self.eggdrop_connect_button.configure(state=disconnected_state)
        self.eggdrop_disconnect_button.configure(state=connected_state)
        self.eggdrop_handle_button.configure(state=connected_state)
        self.eggdrop_password_button.configure(state=connected_state)
        self.eggdrop_send_button.configure(state=connected_state)
        self.eggdrop_input_entry.configure(state=connected_state)
        self._update_eggdrop_tunnel_state()

    def _write_eggdrop_diagnostic(
        self, host: str, port: int, action: str, ok: bool, error_message: str
    ) -> None:
        if not self.diagnostic_logging_var.get():
            return
        log_path = self.diagnostic_log_path_var.get().strip()
        if not log_path:
            return
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "transport": "eggdrop-telnet",
            "endpoint": f"{host}:{port}",
            "action": action,
            "ok": ok,
        }
        if error_message:
            entry["error_message"] = _short_error(error_message)
        _append_diagnostic_log(Path(log_path), entry)

    def _append_eggdrop_output(self, text: str, tag: str) -> None:
        self.eggdrop_output.insert("end", text, (tag,))
        self.eggdrop_output.see("end")

    def _configure_eggdrop_output_tags(self) -> None:
        colours = _output_colours(self.theme_var.get())
        self.eggdrop_output.configure(
            background=colours["background"],
            foreground=colours["foreground"],
            insertbackground=colours["foreground"],
            selectbackground=colours["selection"],
        )
        self.eggdrop_output.tag_configure(
            "eggdrop_data", foreground=colours["foreground"]
        )
        self.eggdrop_output.tag_configure(
            "eggdrop_input", foreground=colours["command"]
        )
        self.eggdrop_output.tag_configure(
            "eggdrop_status", foreground=colours["reply"]
        )
        self.eggdrop_output.tag_configure(
            "eggdrop_error", foreground=colours["error"]
        )

    def _clear_eggdrop_output(self) -> None:
        self.eggdrop_output.delete("1.0", "end")

    def _copy_eggdrop_output(self) -> None:
        text = self.eggdrop_output.get("1.0", "end-1c")
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.eggdrop_status_var.set("Eggdrop transcript copied")

    def _copy_selected_eggdrop_output(self) -> None:
        try:
            text = self.eggdrop_output.get("sel.first", "sel.last")
        except tk.TclError:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.eggdrop_status_var.set("Eggdrop selection copied")

    def _show_eggdrop_output_menu(self, event: tk.Event) -> None:
        has_selection = bool(self.eggdrop_output.tag_ranges("sel"))
        has_output = bool(self.eggdrop_output.get("1.0", "end-1c"))
        self.eggdrop_output_menu.entryconfigure(
            "Copy selected", state=_menu_state(has_selection)
        )
        self.eggdrop_output_menu.entryconfigure(
            "Copy all", state=_menu_state(has_output)
        )
        self.eggdrop_output_menu.entryconfigure(
            "Clear output", state=_menu_state(has_output)
        )
        self.eggdrop_output_menu.tk_popup(event.x_root, event.y_root)
        self.eggdrop_output_menu.grab_release()

    def _record_eggdrop_input_history(self, line: str) -> None:
        line = line.strip()
        if not line or _is_sensitive_command(line):
            return
        self.eggdrop_input_history = [
            item for item in self.eggdrop_input_history if item != line
        ]
        self.eggdrop_input_history.insert(0, line)
        del self.eggdrop_input_history[50:]

    def _eggdrop_history_previous(self, _event: tk.Event) -> str:
        if not self.eggdrop_input_history:
            return "break"
        if self.eggdrop_history_index is None:
            self.eggdrop_history_index = 0
        else:
            self.eggdrop_history_index = min(
                self.eggdrop_history_index + 1,
                len(self.eggdrop_input_history) - 1,
            )
        self.eggdrop_input_var.set(
            self.eggdrop_input_history[self.eggdrop_history_index]
        )
        self.eggdrop_input_entry.icursor("end")
        return "break"

    def _eggdrop_history_next(self, _event: tk.Event) -> str:
        if self.eggdrop_history_index is None:
            return "break"
        if self.eggdrop_history_index <= 0:
            self.eggdrop_history_index = None
            self.eggdrop_input_var.set("")
        else:
            self.eggdrop_history_index -= 1
            self.eggdrop_input_var.set(
                self.eggdrop_input_history[self.eggdrop_history_index]
            )
            self.eggdrop_input_entry.icursor("end")
        return "break"

    def _record_history(self, command: str) -> None:
        if _is_sensitive_command(command):
            return
        if command in self.command_history:
            self.command_history.remove(command)
        self.command_history.insert(0, command)
        del self.command_history[20:]
        self.command_entry.configure(values=self.command_history)

    def _record_server_settings(self) -> None:
        self.ssh_user_history = _record_value_history(
            self.ssh_user_var.get(), self.ssh_user_history
        )
        self.ssh_host_history = _record_value_history(
            self.ssh_host_var.get(), self.ssh_host_history
        )
        self.ssh_user_entry.configure(values=self.ssh_user_history)
        self.ssh_host_entry.configure(values=self.ssh_host_history)
        self.eggdrop_ssh_user_history = _record_value_history(
            self.eggdrop_ssh_user_var.get(), self.eggdrop_ssh_user_history
        )
        self.eggdrop_ssh_host_history = _record_value_history(
            self.eggdrop_ssh_host_var.get(), self.eggdrop_ssh_host_history
        )
        self.eggdrop_remote_port_history = _record_value_history(
            self.eggdrop_remote_port_var.get(),
            self.eggdrop_remote_port_history,
        )
        self.eggdrop_ssh_user_entry.configure(
            values=self.eggdrop_ssh_user_history
        )
        self.eggdrop_ssh_host_entry.configure(
            values=self.eggdrop_ssh_host_history
        )
        self.eggdrop_remote_port_entry.configure(
            values=self.eggdrop_remote_port_history
        )

    def _current_settings(self) -> dict[str, object]:
        self._record_server_settings()
        port_text = self.port_var.get().strip()
        try:
            port = int(port_text)
        except ValueError:
            port = DEFAULT_PORT
        return {
            "mode": self.mode_var.get(),
            "socket": self.socket_var.get().strip(),
            "host": self.host_var.get().strip(),
            "port": port,
            "ssh_host": self.ssh_host_var.get().strip(),
            "ssh_port": _port_or_default(
                self.ssh_port_var.get(), DEFAULT_SSH_PORT
            ),
            "ssh_user": self.ssh_user_var.get().strip(),
            "ssh_command": self._ssh_command(),
            "remote_path": self.remote_path_var.get().strip(),
            "theme": self.theme_var.get(),
            "diagnostic_logging_enabled": self.diagnostic_logging_var.get(),
            "diagnostic_log_path": self.diagnostic_log_path_var.get().strip(),
            "eggdrop_profile": self.eggdrop_profile_var.get().strip(),
            "eggdrop_host": self.eggdrop_host_var.get().strip(),
            "eggdrop_port": _port_or_default(
                self.eggdrop_port_var.get(), DEFAULT_EGGDROP_PORT
            ),
            "eggdrop_handle": self.eggdrop_handle_var.get().strip(),
            "eggdrop_ssh_host": self.eggdrop_ssh_host_var.get().strip(),
            "eggdrop_ssh_port": _port_or_default(
                self.eggdrop_ssh_port_var.get(), DEFAULT_EGGDROP_SSH_PORT
            ),
            "eggdrop_ssh_user": self.eggdrop_ssh_user_var.get().strip(),
            "eggdrop_remote_host": self.eggdrop_remote_host_var.get().strip(),
            "eggdrop_remote_port": _port_or_default(
                self.eggdrop_remote_port_var.get(),
                DEFAULT_EGGDROP_REMOTE_PORT,
            ),
            "eggdrop_input_history": self.eggdrop_input_history,
            "last_command": self.command_var.get().strip(),
            "command_history": self.command_history,
            "ssh_user_history": self.ssh_user_history,
            "ssh_host_history": self.ssh_host_history,
            "eggdrop_ssh_user_history": self.eggdrop_ssh_user_history,
            "eggdrop_ssh_host_history": self.eggdrop_ssh_host_history,
            "eggdrop_remote_port_history": self.eggdrop_remote_port_history,
            "window_geometry": self.root.geometry(),
        }

    def _restore_window_geometry(self) -> None:
        geometry = self.settings.get("window_geometry")
        if isinstance(geometry, str) and _is_valid_window_geometry(geometry):
            self.root.geometry(geometry)

    def _ssh_command(self) -> str:
        if not IS_LINUX:
            return ""
        return self.ssh_command_var.get().strip()

    def _save_settings(self) -> None:
        _save_settings(self._current_settings())

    def _close(self) -> None:
        self._close_eggdrop_socket()
        self._close_eggdrop_tunnel()
        self._save_settings()
        self.root.destroy()

    def _append_output(self, text: str) -> None:
        self.output.insert("end", text)
        self.output.see("end")

    def _append_command_output(
        self, timestamp: str, command: str, prefix: str, message: str, ok: bool
    ) -> None:
        label_tag = "reply_label" if ok else "error_label"
        body_tag = "reply_body" if ok else "error_body"
        self.output.insert(
            "end", f"[{timestamp}] {command}\n", ("command_header",)
        )
        self.output.insert("end", f"{prefix}:\n", (label_tag,))
        self.output.insert("end", f"{message}\n\n", (body_tag,))
        self.output.see("end")

    def _configure_output_tags(self) -> None:
        colours = _output_colours(self.theme_var.get())
        self.output.configure(
            background=colours["background"],
            foreground=colours["foreground"],
            insertbackground=colours["foreground"],
            selectbackground=colours["selection"],
        )
        self.output.tag_configure(
            "command_header", foreground=colours["command"]
        )
        self.output.tag_configure("reply_label", foreground=colours["reply"])
        self.output.tag_configure(
            "reply_body", foreground=colours["foreground"]
        )
        self.output.tag_configure("error_label", foreground=colours["error"])
        self.output.tag_configure(
            "error_body", foreground=colours["error_body"]
        )

    def _clear_output(self) -> None:
        self.output.delete("1.0", "end")

    def _copy_output(self) -> None:
        text = self.output.get("1.0", "end-1c")
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set("Output copied")

    def _copy_last_failed_diagnostic(self) -> None:
        if not self.last_failed_diagnostic:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.last_failed_diagnostic)
        self.status_var.set("Diagnostics copied")

    def _set_last_failed_diagnostic(self, diagnostic: str) -> None:
        self.last_failed_diagnostic = diagnostic
        self.copy_diagnostics_button.configure(
            state=_menu_state(self.last_failed_diagnostic)
        )

    def _show_output_menu(self, event: tk.Event) -> None:
        self.output_context_index = self.output.index(f"@{event.x},{event.y}")
        has_selection = bool(self.output.tag_ranges("sel"))
        command = self._context_command()
        self.output_menu.entryconfigure(
            "Cut selected", state=_menu_state(has_selection)
        )
        self.output_menu.entryconfigure(
            "Copy selected", state=_menu_state(has_selection)
        )
        self.output_menu.entryconfigure(
            "Copy all", state=_menu_state(self._has_output())
        )
        self.output_menu.entryconfigure(
            "Copy command", state=_menu_state(command)
        )
        self.output_menu.entryconfigure(
            "Re-run command", state=_menu_state(command)
        )
        self.output_menu.entryconfigure(
            "Clear output", state=_menu_state(self._has_output())
        )
        self.output_menu.tk_popup(event.x_root, event.y_root)
        self.output_menu.grab_release()

    def _show_command_menu(self, event: tk.Event) -> None:
        has_selection = bool(self.command_entry.selection_present())
        has_text = bool(self.command_var.get())
        self.command_menu.entryconfigure(
            "Cut", state=_menu_state(has_selection)
        )
        self.command_menu.entryconfigure(
            "Copy", state=_menu_state(has_selection)
        )
        self.command_menu.entryconfigure(
            "Select all", state=_menu_state(has_text)
        )
        self.command_menu.tk_popup(event.x_root, event.y_root)
        self.command_menu.grab_release()

    def _show_settings_menu(self, event: tk.Event) -> None:
        self.settings_context_widget = event.widget
        has_selection = _entry_has_selection(event.widget)
        has_text = _entry_has_text(event.widget)
        is_editable = _entry_is_editable(event.widget)
        self.settings_menu.entryconfigure(
            "Cut", state=_menu_state(has_selection and is_editable)
        )
        self.settings_menu.entryconfigure(
            "Copy", state=_menu_state(has_selection)
        )
        self.settings_menu.entryconfigure(
            "Paste", state=_menu_state(is_editable)
        )
        self.settings_menu.entryconfigure(
            "Select all", state=_menu_state(has_text)
        )
        self.settings_menu.tk_popup(event.x_root, event.y_root)
        self.settings_menu.grab_release()

    def _copy_selected(self) -> None:
        try:
            text = self.output.get("sel.first", "sel.last")
        except tk.TclError:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set("Selection copied")

    def _copy_selected_output(self, _event: tk.Event | None = None) -> str:
        self._copy_selected()
        return "break"

    def _cut_selected_output(self, _event: tk.Event | None = None) -> str:
        try:
            text = self.output.get("sel.first", "sel.last")
        except tk.TclError:
            return "break"
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.output.delete("sel.first", "sel.last")
        self.status_var.set("Selection cut")
        return "break"

    def _delete_output_selection_or_block(self, _event: tk.Event) -> str:
        try:
            self.output.delete("sel.first", "sel.last")
            self.status_var.set("Selection deleted")
        except tk.TclError:
            if self._delete_context_block(self.output.index("insert")):
                self.status_var.set("Entry deleted")
        return "break"

    def _handle_output_keypress(self, event: tk.Event) -> str | None:
        if _is_output_delete_key(event):
            return self._delete_output_selection_or_block(event)
        return None

    def _handle_root_delete_key(self, event: tk.Event) -> str | None:
        if self.root.focus_get() == self.output and _is_output_delete_key(
            event
        ):
            return self._delete_output_selection_or_block(event)
        return None

    def _delete_context_block(self, index: str) -> bool:
        start_line = self._context_header_line(index)
        if start_line is None:
            return False

        end_line = start_line + 1
        last_line = int(self.output.index("end-1c").split(".", 1)[0])
        while end_line <= last_line:
            line = self.output.get(f"{end_line}.0", f"{end_line}.end")
            if end_line > start_line and _command_from_output_header(line):
                break
            end_line += 1

        self.output.delete(f"{start_line}.0", f"{end_line}.0")
        return True

    def _copy_context_command(self) -> None:
        command = self._context_command()
        if not command:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(command)
        self.status_var.set("Command copied")

    def _rerun_context_command(self) -> None:
        command = self._context_command()
        if command:
            self._send(command)

    def _context_command(self) -> str:
        line_number = self._context_header_line(self.output_context_index)
        if line_number is None:
            return ""
        line = self.output.get(f"{line_number}.0", f"{line_number}.end")
        return _command_from_output_header(line)

    def _context_header_line(self, index: str) -> int | None:
        line_number = int(self.output.index(index).split(".", 1)[0])
        while line_number > 0:
            line = self.output.get(f"{line_number}.0", f"{line_number}.end")
            if _command_from_output_header(line):
                return line_number
            line_number -= 1
        return None

    def _has_output(self) -> bool:
        return bool(self.output.get("1.0", "end-1c"))

    def _cut_command(self, _event: tk.Event | None = None) -> str:
        self._copy_command()
        try:
            self.command_entry.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        return "break"

    def _copy_command(self, _event: tk.Event | None = None) -> str:
        try:
            text = self.command_entry.selection_get()
        except tk.TclError:
            return "break"
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        return "break"

    def _paste_command(self, _event: tk.Event | None = None) -> str:
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return "break"
        self.command_entry.insert("insert", text)
        return "break"

    def _select_command(self, _event: tk.Event | None = None) -> str:
        self.command_entry.selection_range(0, "end")
        self.command_entry.icursor("end")
        return "break"

    def _settings_widget(self, event: tk.Event | None):
        if event is not None:
            self.settings_context_widget = event.widget
        return self.settings_context_widget

    def _cut_settings_field(self, event: tk.Event | None = None) -> str:
        widget = self._settings_widget(event)
        if widget is None or not _entry_is_editable(widget):
            return "break"
        self._copy_settings_field(event)
        try:
            widget.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        return "break"

    def _copy_settings_field(self, event: tk.Event | None = None) -> str:
        widget = self._settings_widget(event)
        if widget is None:
            return "break"
        try:
            text = widget.selection_get()
        except tk.TclError:
            return "break"
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        return "break"

    def _paste_settings_field(self, event: tk.Event | None = None) -> str:
        widget = self._settings_widget(event)
        if widget is None or not _entry_is_editable(widget):
            return "break"
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return "break"
        widget.insert("insert", text)
        return "break"

    def _select_settings_field(self, event: tk.Event | None = None) -> str:
        widget = self._settings_widget(event)
        if widget is None:
            return "break"
        widget.selection_range(0, "end")
        widget.icursor("end")
        return "break"

    def _delete_settings_field(self, event: tk.Event | None = None) -> str:
        widget = self._settings_widget(event)
        if widget is None or not _entry_is_editable(widget):
            return "break"
        try:
            widget.delete("sel.first", "sel.last")
        except tk.TclError:
            widget.delete("insert")
        return "break"

    def _handle_settings_keypress(self, event: tk.Event) -> str | None:
        if _is_output_delete_key(event):
            return self._delete_settings_field(event)
        return None

    def _select_output(self, _event: tk.Event | None = None) -> str:
        self.output.tag_add("sel", "1.0", "end-1c")
        self.output.mark_set("insert", "1.0")
        self.output.see("insert")
        return "break"


def _entry_is_editable(widget) -> bool:
    try:
        return str(widget.cget("state")) not in {"disabled", "readonly"}
    except tk.TclError:
        return True


def _entry_has_selection(widget) -> bool:
    try:
        return bool(widget.selection_present())
    except (AttributeError, tk.TclError):
        return False


def _entry_has_text(widget) -> bool:
    try:
        return bool(widget.get())
    except (AttributeError, tk.TclError):
        return False


def _is_output_delete_key(event: tk.Event) -> bool:
    keysym = str(getattr(event, "keysym", ""))
    keycode = int(getattr(event, "keycode", 0) or 0)
    if keysym in {"Delete", "KP_Delete", "KP_Decimal", "KP_Separator"}:
        return True
    if keysym == "KP_Period":
        return True
    # X11 commonly reports the keypad decimal/delete key as keycode 91.
    return os.name != "nt" and keycode == 91


def send_socket_command(socket_path: str, command: str) -> str:
    if not socket_path:
        raise ValueError("Socket path is required.")
    if not os.path.exists(socket_path):
        raise FileNotFoundError(f"Socket not found: {socket_path}")

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(REQUEST_TIMEOUT_SECONDS)
        client.connect(socket_path)
        _send_socket_line(client, command)
        return _read_socket_reply(client)


def send_tcp_command(host: str, port: int, command: str) -> str:
    if not host:
        raise ValueError("Host is required.")
    if port < 1 or port > 65535:
        raise ValueError("Port must be between 1 and 65535.")

    with socket.create_connection(
        (host, port), timeout=REQUEST_TIMEOUT_SECONDS
    ) as client:
        client.settimeout(REQUEST_TIMEOUT_SECONDS)
        _send_socket_line(client, command, shutdown_write=False)
        return _read_socket_reply(client)


def send_ssh_command(
    host: str,
    port: int,
    username: str,
    ssh_command: str,
    remote_path: str,
    command: str,
) -> str:
    if not host:
        raise ValueError("SSH host is required.")
    if not username:
        raise ValueError("SSH user is required.")
    if not remote_path:
        raise ValueError("Remote path is required.")
    if port < 1 or port > 65535:
        raise ValueError("SSH port must be between 1 and 65535.")

    ssh_parts = _ssh_command_parts(ssh_command)
    remote_command = "cd %s && ./botctl exec %s" % (
        _quote_remote_path(remote_path),
        shlex.quote(command),
    )
    # Arguments are passed as a list with shell=False; the remote command is quoted.
    process = subprocess.run(  # nosec B603
        ssh_parts
        + [
            "-p",
            str(port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=%d" % int(REQUEST_TIMEOUT_SECONDS),
            f"{username}@{host}",
            remote_command,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=REQUEST_TIMEOUT_SECONDS,
        check=False,
        **_subprocess_window_kwargs(),
    )
    output = process.stdout[:MAX_REPLY_BYTES].strip()
    error = process.stderr[:MAX_REPLY_BYTES].strip()
    if process.returncode != 0:
        raise RuntimeError(
            _ssh_error_message(error or output or "SSH command failed")
        )
    return output or "(no reply)"


def test_ssh_connection(
    host: str,
    port: int,
    username: str,
    ssh_command: str,
    remote_path: str,
) -> str:
    if not host:
        raise ValueError("SSH host is required.")
    if not username:
        raise ValueError("SSH user is required.")
    if not remote_path:
        raise ValueError("Remote path is required.")
    if port < 1 or port > 65535:
        raise ValueError("SSH port must be between 1 and 65535.")

    ssh_parts = _ssh_command_parts(ssh_command)
    remote_command = "cd %s && test -x ./botctl" % _quote_remote_path(
        remote_path
    )
    process = subprocess.run(  # nosec B603
        ssh_parts
        + [
            "-p",
            str(port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=%d" % int(REQUEST_TIMEOUT_SECONDS),
            f"{username}@{host}",
            remote_command,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=REQUEST_TIMEOUT_SECONDS,
        check=False,
        **_subprocess_window_kwargs(),
    )
    output = process.stdout[:MAX_REPLY_BYTES].strip()
    error = process.stderr[:MAX_REPLY_BYTES].strip()
    if process.returncode != 0:
        raise RuntimeError(
            _ssh_error_message(error or output or "SSH connection test failed")
        )
    return "SSH authentication and remote path look OK."


def start_eggdrop_ssh_tunnel(
    profile: dict[str, object],
) -> subprocess.Popen:
    local_port = int(profile["port"])
    remote_host = str(profile.get("remote_host", "127.0.0.1"))
    remote_port = int(profile.get("remote_port", local_port))
    ssh_user = str(profile.get("ssh_user", ""))
    ssh_host = str(profile.get("ssh_host", ""))
    ssh_port = int(profile.get("ssh_port", 22))
    if not ssh_user:
        raise ValueError("SSH user is required for this Eggdrop profile.")
    if not ssh_host:
        raise ValueError("SSH host is required for this Eggdrop profile.")

    process = subprocess.Popen(  # nosec B603
        [
            _find_ssh_executable(),
            "-N",
            "-L",
            f"{local_port}:{remote_host}:{remote_port}",
            "-p",
            str(ssh_port),
            "-o",
            "BatchMode=yes",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=%d" % int(REQUEST_TIMEOUT_SECONDS),
            f"{ssh_user}@{ssh_host}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **_subprocess_window_kwargs(),
    )
    time.sleep(0.5)
    if process.poll() is not None:
        error = process.stderr.read() if process.stderr is not None else ""
        raise RuntimeError(
            _short_error(error or "SSH tunnel failed to start.")
        )
    return process


def connect_eggdrop_endpoint(
    host: str, port: int, tunnel_process: subprocess.Popen | None = None
) -> socket.socket:
    deadline = time.monotonic() + REQUEST_TIMEOUT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if tunnel_process is not None and tunnel_process.poll() is not None:
            error = (
                tunnel_process.stderr.read()
                if tunnel_process.stderr is not None
                else ""
            )
            error = _short_error(error or "SSH tunnel exited early.")
            raise RuntimeError(
                "SSH tunnel exited before the local endpoint became "
                f"reachable: {error}"
            )
        try:
            return socket.create_connection((host, port), timeout=1.0)
        except OSError as exc:
            last_error = exc
            time.sleep(0.2)
    if tunnel_process is not None and tunnel_process.poll() is None:
        raise TimeoutError(
            "Timed out waiting for the local Eggdrop endpoint; the SSH tunnel "
            "process is still running but the local port did not accept a "
            "connection."
        )
    if last_error is not None:
        raise last_error
    raise TimeoutError("Timed out waiting for Eggdrop endpoint.")


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def _write_eggdrop_diagnostic_entry(
    diagnostic: dict[str, object],
    endpoint: str,
    action: str,
    ok: bool,
    error_message: str,
) -> None:
    if not diagnostic.get("enabled"):
        return
    log_path = str(diagnostic.get("path", "")).strip()
    if not log_path:
        return
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "transport": "eggdrop-telnet",
        "endpoint": endpoint,
        "action": action,
        "ok": ok,
    }
    if error_message:
        entry["error_message"] = _short_error(error_message)
    _append_diagnostic_log(Path(log_path), entry)


def _format_diagnostic_copy(entry: dict[str, object]) -> str:
    return json.dumps(entry, indent=2, sort_keys=True) + "\n"


def _ssh_error_message(message: str) -> str:
    if "Permission denied" not in message:
        return message
    return "SSH authentication failed. Configure a Windows OpenSSH key or ssh-agent identity for this host."


def _send_socket_line(
    client: socket.socket, command: str, shutdown_write: bool = True
) -> None:
    client.sendall((command + "\n").encode("utf-8"))
    if not shutdown_write:
        return
    try:
        client.shutdown(socket.SHUT_WR)
    except OSError:
        pass


def _read_socket_reply(client: socket.socket) -> str:
    chunks = []
    received = 0
    deadline = time.monotonic() + REQUEST_TIMEOUT_SECONDS
    while received < MAX_REPLY_BYTES:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Timed out waiting for reply.")
        client.settimeout(min(SOCKET_READ_IDLE_SECONDS, remaining))
        try:
            chunk = client.recv(
                min(REPLY_CHUNK_BYTES, MAX_REPLY_BYTES - received)
            )
        except socket.timeout:
            if chunks:
                break
            continue
        if not chunk:
            break
        chunks.append(chunk)
        received += len(chunk)

    if received >= MAX_REPLY_BYTES:
        chunks.append(b"\n[reply truncated]")
    return b"".join(chunks).decode("utf-8", errors="replace").strip()


def _decode_eggdrop_bytes(data: bytes) -> str:
    # Drop simple Telnet negotiation bytes so the transcript stays readable.
    output = bytearray()
    index = 0
    while index < len(data):
        byte = data[index]
        if byte == 255:
            index += 3
            continue
        output.append(byte)
        index += 1
    return bytes(output).decode("utf-8", errors="replace")


def _find_ssh_executable() -> str:
    candidates = ("ssh.exe", "ssh") if os.name == "nt" else ("ssh", "ssh.exe")
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise RuntimeError("OpenSSH client not found. Install ssh.exe or ssh.")


def _subprocess_window_kwargs() -> dict[str, object]:
    if os.name != "nt":
        return {}

    kwargs: dict[str, object] = {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    kwargs["startupinfo"] = startupinfo
    return kwargs


def _ssh_command_parts(ssh_command: str) -> list[str]:
    if ssh_command.strip():
        parts = shlex.split(ssh_command, posix=os.name != "nt")
        if parts:
            executable = Path(parts[0]).name.lower()
            if executable in SSH_EXECUTABLES:
                return parts
            raise RuntimeError("SSH client must be ssh or ssh.exe.")
        raise RuntimeError("SSH client command is empty.")
    return [_find_ssh_executable()]


def _ssh_command_label(ssh_command: str) -> str:
    if ssh_command.strip():
        return ssh_command.strip()
    return _find_ssh_executable()


def _command_from_output_header(line: str) -> str:
    if not line.startswith("["):
        return ""
    marker = "] "
    if marker not in line:
        return ""
    return line.split(marker, 1)[1].strip()


def _menu_state(enabled: object) -> str:
    return "normal" if enabled else "disabled"


def _port_or_default(port_text: str, default: int) -> int:
    try:
        return int(port_text)
    except ValueError:
        return default


def _normalise_remote_path(remote_path: str) -> str:
    remote_path = remote_path.strip()
    if not remote_path:
        return remote_path
    if remote_path == "~":
        return remote_path
    if remote_path.startswith("~/"):
        return remote_path

    home_match = re.match(r"^/(?:home|Users)/[^/]+(?:/(.*))?$", remote_path)
    if not home_match:
        return remote_path

    remainder = home_match.group(1) or ""
    if not remainder:
        return "~"
    return "~/" + remainder


def _quote_remote_path(remote_path: str) -> str:
    remote_path = _normalise_remote_path(remote_path)
    if remote_path == "~":
        return "$HOME"
    if remote_path.startswith("~/"):
        return "$HOME/" + shlex.quote(remote_path[2:])
    return shlex.quote(remote_path)


def _is_valid_window_geometry(geometry: str) -> bool:
    return bool(WINDOW_GEOMETRY_RE.match(geometry))


def _format_status_probe(
    active_mode: str,
    socket_exists: bool,
    unix_checked: bool,
    unix_ok: bool,
    tcp_checked: bool,
    tcp_ok: bool,
    ssh_ok: bool | None,
    details: list[str],
    include_unix: bool = True,
    include_tcp: bool = True,
) -> str:
    unix_state = "inactive"
    if unix_checked:
        unix_state = "responding" if unix_ok else "not reachable"
    tcp_state = "inactive"
    if tcp_checked:
        tcp_state = "responding" if tcp_ok else "not reachable"
    lines = [
        "Active transport: %s" % active_mode.upper(),
    ]
    if include_unix:
        lines.extend(
            [
                "UNIX socket: %s"
                % ("present" if socket_exists else "missing"),
                "LocalControl via UNIX: %s" % unix_state,
            ]
        )
    if include_tcp:
        lines.append("LocalControl via TCP: %s" % tcp_state)
    if ssh_ok is not None:
        lines.append(
            "LocalControl via SSH: %s"
            % ("responding" if ssh_ok else "not reachable")
        )
    if details:
        lines.append("Details:")
        lines.extend(details)
    return "\n".join(lines)


def _output_colours(theme: str) -> dict[str, str]:
    if theme == "light":
        return {
            "background": "#ffffff",
            "foreground": "#1f2937",
            "selection": "#bfdbfe",
            "command": "#1d4ed8",
            "reply": "#047857",
            "error": "#b91c1c",
            "error_body": "#7f1d1d",
        }
    return {
        "background": "#1f2328",
        "foreground": "#d0d7de",
        "selection": "#264f78",
        "command": "#8ab4f8",
        "reply": "#7ee787",
        "error": "#ff7b72",
        "error_body": "#ffa198",
    }


def _windows_mono_font(root: tk.Tk):
    if os.name != "nt":
        return None
    available_fonts = set(tkfont.families(root))
    for family in ("Cascadia Mono", "Consolas", "Courier New"):
        if family in available_fonts:
            return (family, 10)
    return None


def _help_text() -> str:
    transport_lines = [
        "SSH: runs botctl on the remote machine through OpenSSH."
    ]
    if IS_LINUX:
        transport_lines.insert(
            0,
            "TCP socket: use host 127.0.0.1 and the configured LocalControl TCP "
            "port for local Linux testing.",
        )
        transport_lines.insert(
            0,
            "UNIX socket: fastest local path when the GUI and bot share the same "
            "Linux filesystem.",
        )
        platform_lines = [
            "Linux can use UNIX socket, TCP socket, or SSH mode.",
            "The SSH client field is available for testing a specific ssh command.",
        ]
    else:
        platform_lines = [
            "Windows uses SSH mode for Limnoria control.",
            "Windows SSH mode uses native OpenSSH. Configure a Windows key or "
            "ssh-agent identity first; GUI password prompts are not available.",
            "Use the Linux GUI for WSL-local Limnoria bots.",
        ]

    lines = [
        "F.A.B. Help",
        "",
        "Mission briefing",
        "The Limnoria tab sends one command at a time through the LocalControl "
        "plugin and displays the reply or error.",
        "The Eggdrop tab is a separate interactive Telnet session for direct "
        "or SSH-tunnelled Eggdrop partyline access.",
        "",
        "Transports",
        *transport_lines,
        "",
        "Platform notes",
        *platform_lines,
        "",
        "Diagnostics",
        "Enable diagnostics in Settings when testing a failure. The log is JSON "
        "lines and records metadata only: timestamp, transport, endpoint, command "
        "summary, duration, and short error details.",
        "Replies, full command text, and Eggdrop passwords are not written to the "
        "diagnostics log.",
        "",
        "Files",
        f"Settings file: {SETTINGS_FILE}",
        f"Default diagnostics log: {DEFAULT_DIAGNOSTIC_LOG}",
        "",
        "Troubleshooting",
        "Wrong TCP port: confirm the bot TCP listener is enabled and the port "
        "matches the plugin setting.",
        "SSH auth failure: confirm OpenSSH can connect in batch mode before using "
        "the GUI.",
        "No reply: try sysinfo first, then check the bot and LocalControl plugin "
        "are loaded.",
        "",
        "F.A.B.",
    ]
    return "\n".join(lines)


def _load_settings() -> dict[str, object]:
    _migrate_legacy_settings_file()
    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data, dict):
        if data.get("mode") == "telnet":
            data["mode"] = "tcp"
        remote_path = data.get("remote_path")
        if isinstance(remote_path, str):
            data["remote_path"] = _normalise_remote_path(remote_path)
        return data
    return {}


def _save_settings(settings: dict[str, object]) -> None:
    settings = dict(settings)
    settings["command_history"] = [
        command
        for command in settings.get("command_history", [])
        if isinstance(command, str) and not _is_sensitive_command(command)
    ]
    settings["eggdrop_input_history"] = [
        command
        for command in settings.get("eggdrop_input_history", [])
        if isinstance(command, str)
        and command.strip()
        and not _is_sensitive_command(command)
    ][:50]
    if _is_sensitive_command(str(settings.get("last_command", ""))):
        settings["last_command"] = "sysinfo"
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(
            json.dumps(settings, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        SETTINGS_FILE.chmod(SETTINGS_FILE_MODE)
    except OSError:
        pass


def _append_diagnostic_log(log_path: Path, entry: dict[str, object]) -> None:
    try:
        log_path = log_path.expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        log_path.chmod(DIAGNOSTIC_LOG_MODE)
    except OSError:
        pass


def _legacy_settings_file() -> Path:
    return Path(__file__).with_name("botctl_gui.json")


def _migrate_legacy_settings_file() -> None:
    legacy_file = _legacy_settings_file()
    if SETTINGS_FILE.exists() or not legacy_file.exists():
        return
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(
            legacy_file.read_text(encoding="utf-8"), encoding="utf-8"
        )
        SETTINGS_FILE.chmod(SETTINGS_FILE_MODE)
    except OSError:
        pass


def _normalise_history(saved_history: object) -> list[str]:
    history = []
    if isinstance(saved_history, list):
        for item in saved_history:
            if (
                isinstance(item, str)
                and item.strip()
                and not _is_sensitive_command(item)
            ):
                history.append(item.strip())
    for command in COMMAND_PRESETS:
        if command not in history:
            history.append(command)
    return history[:20]


def _normalise_eggdrop_history(saved_history: object) -> list[str]:
    history = []
    if isinstance(saved_history, list):
        for item in saved_history:
            if (
                isinstance(item, str)
                and item.strip()
                and item.strip() not in history
                and not _is_sensitive_command(item)
            ):
                history.append(item.strip())
    return history[:50]


def _eggdrop_profile_names() -> list[str]:
    return [str(profile["name"]) for profile in DEFAULT_EGGDROP_PROFILES]


def _eggdrop_profile_by_name(name: str) -> dict[str, object] | None:
    for profile in DEFAULT_EGGDROP_PROFILES:
        if profile["name"] == name:
            return dict(profile)
    return None


def _normalise_eggdrop_profile_name(name: str) -> str:
    if name in _eggdrop_profile_names():
        return name
    return "Direct"


def _normalise_value_history(
    saved_history: object, current_value: str
) -> list[str]:
    history = []
    if isinstance(saved_history, list):
        for item in saved_history:
            if (
                isinstance(item, str)
                and item.strip()
                and item.strip() not in history
            ):
                history.append(item.strip())
    if current_value and current_value not in history:
        history.insert(0, current_value)
    return history[:20]


def _record_value_history(value: str, history: list[str]) -> list[str]:
    value = value.strip()
    if not value:
        return history[:20]
    history = [item for item in history if item != value]
    history.insert(0, value)
    return history[:20]


def _bool_setting(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _command_summary(command: str) -> str:
    parts = command.split()
    if not parts:
        return "(empty)"
    if _is_sensitive_command(command):
        return f"{parts[0]} [redacted]"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} [arguments omitted]"


def _short_error(message: str) -> str:
    message = " ".join(message.split())
    if len(message) <= 300:
        return message
    return message[:297] + "..."


def _is_sensitive_command(command: str) -> bool:
    parts = command.split()
    redact_next = False
    for part in parts:
        if redact_next:
            return True
        key, separator, _value = part.partition("=")
        if separator and _is_sensitive_command_key(key):
            return True
        if _is_sensitive_command_key(part):
            redact_next = True
    return False


def _is_sensitive_command_key(value: str) -> bool:
    key = value.lower().strip("-")
    for term in SENSITIVE_COMMAND_TERMS:
        if term in key:
            return True
    for term in SENSITIVE_COMMAND_KEYS:
        if (
            key == term
            or key.endswith(f".{term}")
            or key.endswith(f"_{term}")
            or key.endswith(f"-{term}")
        ):
            return True
    return False


def _apply_theme(theme: str) -> bool:
    try:
        import sv_ttk
    except ImportError:
        return False
    sv_ttk.set_theme(theme)
    return True


def main() -> None:
    root = tk.Tk()
    LocalControlGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
