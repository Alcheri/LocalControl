###
# Copyright (c) 2026, Barry KW Suridge
# All rights reserved.
#
#
###

import unittest
import socket
import tempfile
from pathlib import Path

from supybot import test as supybot_test

try:
    from . import plugin
except ImportError:  # pragma: no cover - allows direct pytest execution.
    import plugin


class LocalControlTestCase(supybot_test.PluginTestCase):
    __test__ = False

    plugins = ("LocalControl",)


class TestLocalControlModule(unittest.TestCase):
    def test_plugin_class_is_available(self):
        self.assertIs(plugin.Class, plugin.LocalControl)

    def test_restrict_socket_permissions_sets_owner_only_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = Path(tmpdir) / "localcontrol.sock"
            socket_path.touch()

            plugin._restrict_socket_permissions(socket_path)

            self.assertEqual(socket_path.stat().st_mode & 0o777, plugin.SOCKET_MODE)

    def test_idle_client_times_out(self):
        class IdleClient:
            def __init__(self):
                self.timeout = None
                self.sent = b""
                self.closed = False

            def settimeout(self, timeout):
                self.timeout = timeout

            def recv(self, size):
                raise socket.timeout()

            def sendall(self, data):
                self.sent += data

            def close(self):
                self.closed = True

        local_control = object.__new__(plugin.LocalControl)
        local_control.registryValue = lambda name: False
        client = IdleClient()

        local_control._handle_client(client)

        self.assertEqual(client.timeout, plugin.CLIENT_TIMEOUT_SECONDS)
        self.assertEqual(client.sent, b"Error: request timed out\n")
        self.assertTrue(client.closed)

    def test_dispatch_uses_lock_around_irc_monkeypatch(self):
        class Client:
            def __init__(self):
                self.sent = b""
                self.closed = False

            def settimeout(self, timeout):
                pass

            def recv(self, size):
                return b"sysinfo\n"

            def sendall(self, data):
                self.sent += data

            def close(self):
                self.closed = True

        class Irc:
            nick = "TestBot"

            def sendMsg(self, msg):
                pass

            def queueMsg(self, msg):
                pass

        class DispatchLock:
            def __init__(self):
                self.inside = False
                self.entered = False

            def __enter__(self):
                self.inside = True
                self.entered = True

            def __exit__(self, exc_type, exc_value, traceback):
                self.inside = False

        local_control = object.__new__(plugin.LocalControl)
        local_control.registryValue = lambda name: False
        local_control._dispatch_lock = DispatchLock()
        dispatch_states = []

        def dispatch(irc, command, args, synthetic_prefix):
            dispatch_states.append(local_control._dispatch_lock.inside)

        local_control._dispatch = dispatch
        original_ircs = plugin.world.ircs
        plugin.world.ircs = [Irc()]

        try:
            local_control._handle_client(Client())
        finally:
            plugin.world.ircs = original_ircs

        self.assertTrue(local_control._dispatch_lock.entered)
        self.assertEqual(dispatch_states, [True])

    def test_socket_request_logging_uses_safe_summary_by_default(self):
        lines = []
        original_info = plugin.log.info
        local_control = object.__new__(plugin.LocalControl)
        local_control.registryValue = lambda name: {
            "socketRequestLogging": True,
            "socketRequestFullCommandLogging": False,
        }[name]

        try:
            plugin.log.info = lines.append
            local_control._log_socket_request(
                1,
                "config networks.Libera.sasl.password hunter2",
                "ok",
                replies=1,
                started=0.0,
            )
        finally:
            plugin.log.info = original_info

        self.assertEqual(len(lines), 1)
        self.assertIn('command="config" argc=2', lines[0])
        self.assertNotIn("hunter2", lines[0])
        self.assertNotIn("full_cmd", lines[0])

    def test_full_command_logging_redacts_sensitive_values(self):
        lines = []
        original_info = plugin.log.info
        local_control = object.__new__(plugin.LocalControl)
        local_control.registryValue = lambda name: {
            "socketRequestLogging": True,
            "socketRequestFullCommandLogging": True,
        }[name]

        try:
            plugin.log.info = lines.append
            local_control._log_socket_request(
                2,
                "config networks.Libera.sasl.password hunter2 api_key=abc123 token xyz",
                "ok",
                replies=1,
                started=0.0,
            )
        finally:
            plugin.log.info = original_info

        self.assertEqual(len(lines), 1)
        self.assertIn('command="config" argc=5', lines[0])
        self.assertIn("full_cmd=", lines[0])
        self.assertNotIn("hunter2", lines[0])
        self.assertNotIn("abc123", lines[0])
        self.assertNotIn("xyz", lines[0])


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
