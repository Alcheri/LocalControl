###
# Copyright (c) 2026, Barry KW Suridge
# All rights reserved.
#
#
###

from supybot import callbacks, ircmsgs, ircutils, log, world
from supybot.commands import *
from supybot.i18n import PluginInternationalization

_ = PluginInternationalization("LocalControl")

import os
import socket
import threading
import time
import itertools
import ipaddress
import errno

CLIENT_TIMEOUT_SECONDS = 5.0
SOCKET_MODE = 0o600
TCP_BACKLOG = 1
TCP_BIND_RETRIES = 10
TCP_BIND_RETRY_DELAY_SECONDS = 0.1
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


def _restrict_socket_permissions(socket_path):
    os.chmod(socket_path, SOCKET_MODE)


def _is_sensitive_command_key(value):
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


def _redact_command_text(command):
    parts = command.split()
    redacted = []
    redact_next = False

    for part in parts:
        if redact_next:
            redacted.append("[redacted]")
            redact_next = False
            continue

        key, separator, value = part.partition("=")
        if separator and _is_sensitive_command_key(key):
            redacted.append(f"{key}=[redacted]")
            continue

        redacted.append(part)
        if _is_sensitive_command_key(part):
            redact_next = True

    return " ".join(redacted)


def _command_summary(command):
    parts = command.split()
    if not parts:
        return "", 0
    return parts[0], len(parts) - 1


def _is_loopback_host(host):
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class LocalControl(callbacks.Plugin):
    """Provides a local-only UNIX socket for issuing bot commands."""

    threaded = True
    _req_counter = itertools.count(1)

    def __init__(self, irc):
        self.__parent = super(LocalControl, self)
        self.__parent.__init__(irc)
        self._dispatch_lock = threading.Lock()

        plugin_dir = os.path.dirname(__file__)
        self.socket_path = os.path.join(plugin_dir, ".localcontrol.sock")

        # Remove stale socket
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.socket_path)
        _restrict_socket_permissions(self.socket_path)
        self.server.listen(1)
        self.server.settimeout(1.0)

        self.tcp_server = self._open_tcp_server()

        threading.Thread(
            target=self._accept_loop, args=(self.server,), daemon=True
        ).start()
        if self.tcp_server is not None:
            threading.Thread(
                target=self._accept_loop, args=(self.tcp_server,), daemon=True
            ).start()

    def die(self):
        try:
            self.server.close()
        except Exception as e:
            log.debug("LocalControl: UNIX socket close failed: %s" % e)
        if self.tcp_server is not None:
            try:
                self.tcp_server.close()
            except Exception as e:
                log.debug("LocalControl: TCP socket close failed: %s" % e)
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass
        self.__parent.die()

    # -----------------------------------------------------------------------------

    def _open_tcp_server(self):
        if not self.registryValue("tcpListenerEnabled"):
            return None

        host = self.registryValue("tcpListenHost")
        port = self.registryValue("tcpListenPort")
        if port < 1 or port > 65535:
            log.warning("LocalControl: TCP listener disabled; invalid port %r" % port)
            return None
        if not self.registryValue("tcpAllowRemote") and not _is_loopback_host(host):
            log.warning(
                "LocalControl: TCP listener disabled; %s is not loopback and "
                "tcpAllowRemote is false" % host
            )
            return None

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if not self._bind_tcp_server(server, host, port):
            return None

        server.listen(TCP_BACKLOG)
        server.settimeout(1.0)
        log.info("LocalControl: TCP listener enabled on %s:%s" % (host, port))
        return server

    # -----------------------------------------------------------------------------

    def _bind_tcp_server(self, server, host, port):
        for attempt in range(TCP_BIND_RETRIES + 1):
            try:
                server.bind((host, port))
                return True
            except OSError as e:
                if e.errno != errno.EADDRINUSE or attempt == TCP_BIND_RETRIES:
                    server.close()
                    log.warning(
                        "LocalControl: TCP listener disabled; bind failed: %s" % e
                    )
                    return False
                time.sleep(TCP_BIND_RETRY_DELAY_SECONDS)
        return False

    # -----------------------------------------------------------------------------

    def _accept_loop(self, server):
        while True:
            try:
                conn, _ = server.accept()
            except socket.timeout:
                if world.dying:
                    return
                continue
            except OSError:
                if world.dying:
                    return
                raise
            threading.Thread(
                target=self._handle_client, args=(conn,), daemon=True
            ).start()

    # ----------------------------------------------------------------------
    def _handle_client(self, conn):
        req_id = next(self._req_counter)
        started = time.perf_counter()
        raw_data = ""

        try:
            conn.settimeout(CLIENT_TIMEOUT_SECONDS)
            # Read the incoming command (single line)
            raw_data = conn.recv(4096).decode("utf-8")
            data = raw_data.strip()

            if not data:
                conn.sendall(b"(no reply)\n")
                self._log_socket_request(
                    req_id, raw_data, "empty", replies=0, started=started
                )
                return

            parts = data.split()
            command = parts[0]
            args = parts[1:]

            # Capture outgoing messages
            replies = []

            synthetic_nick = f"LocalControl{req_id}"
            reply_target = synthetic_nick
            # synthetic_prefix = "Barry!Barry@hello.at.bazzas.club"
            synthetic_prefix = (
                f"LocalControl{req_id}!local{req_id}@localcontrol.invalid"
            )

            # Monkeypatch sendMsg/queueMsg to capture replies
            irc = world.ircs[0]
            old_send = irc.sendMsg
            old_queue = irc.queueMsg

            def capture(msg):
                # Tag outgoing messages so Limnoria treats them as owner-authenticated
                msg.tag("identified", True)
                msg.tag("authenticated", True)
                msg.tag("account", "owner")
                msg.tag("capability", "owner")

                # Capture PRIVMSG/NOTICE replies addressed to our synthetic nick
                if msg.command in ("PRIVMSG", "NOTICE") and len(msg.args) >= 2:
                    if ircutils.strEqual(msg.args[0], reply_target):
                        replies.append(msg.args[1])
                        return True
                return False

            def send_cb(msg):
                if not capture(msg):
                    old_send(msg)

            def queue_cb(msg):
                if not capture(msg):
                    old_queue(msg)

            with self._dispatch_lock:
                irc.sendMsg = send_cb
                irc.queueMsg = queue_cb

                try:
                    # Dispatch the command
                    self._dispatch(irc, command, args, synthetic_prefix)
                finally:
                    # Restore original methods
                    irc.sendMsg = old_send
                    irc.queueMsg = old_queue

            # Build reply text
            if replies:
                reply_text = "\n".join(replies) + "\n"
            else:
                reply_text = "(no reply)\n"

            conn.sendall(reply_text.encode("utf-8"))

            # Log the request
            self._log_socket_request(
                req_id, raw_data, "ok", replies=len(replies), started=started
            )

        except socket.timeout:
            err = "Error: request timed out\n"
            conn.sendall(err.encode("utf-8"))
            self._log_socket_request(
                req_id, raw_data, "timeout", replies=0, started=started
            )

        except Exception as e:
            err = f"Error: {e}\n"
            conn.sendall(err.encode("utf-8"))
            self._log_socket_request(req_id, raw_data, err, replies=0, started=started)

        finally:
            conn.close()

    def _log_socket_request(
        self, req_id, command, status, replies, started, error=None
    ):
        if not self.registryValue("socketRequestLogging"):
            return
        duration_ms = (time.perf_counter() - started) * 1000.0
        cmd, argc = _command_summary(command)
        line = (
            "LocalControl: socket req=%s status=%s replies=%s ms=%.1f "
            'command="%s" argc=%s'
        ) % (
            req_id,
            status,
            replies,
            duration_ms,
            cmd,
            argc,
        )
        if self.registryValue("socketRequestFullCommandLogging"):
            full_cmd = _redact_command_text(" ".join(command.split()))[:200]
            line += ' full_cmd="%s"' % full_cmd
        if error:
            err = " ".join(error.split())[:200]
            line += ' error="%s"' % err
        log.info(line)

    # ----------------------------------------------------------------------

    def _getIrc(self):
        # In Limnoria, active IRC connections are tracked in world.ircs.
        # Prefer a bound irc instance if present, otherwise use the first live one.
        if hasattr(self, "irc") and self.irc is not None:  # type: ignore[attr-defined]
            return self.irc  # type: ignore[attr-defined]
        if getattr(world, "ircs", None):
            return world.ircs[0]
        raise RuntimeError("No IRC object is available for LocalControl")

    # ----------------------------------------------------------------------
    def _dispatch(self, baseIrc, command, args, synthetic_prefix):
        # Build the payload exactly as a user would type it
        payload = " ".join([command] + args)

        # Construct the synthetic PRIVMSG that delivers the command to the bot
        msg = ircmsgs.privmsg(baseIrc.nick, payload, prefix=synthetic_prefix)

        # Mark the synthetic user as authenticated/owner so Limnoria trusts it
        msg.tag("identified", True)
        msg.tag("authenticated", True)
        msg.tag("account", "owner")  # type: ignore[arg-type]
        msg.tag("capability", "owner")  # type: ignore[arg-type]

        # Feed the message into Limnoria's parser
        baseIrc.feedMsg(msg)

    # ----------------------------------------------------------------------
    def sysinfo(self, irc, msg, args):
        """sysinfo

        Show basic bot and system information.
        """
        import platform
        import sys
        import supybot.version as v

        bot_nick = irc.nick
        limnoria_version = v.version
        python_version = sys.version.split()[0]

        os_name = platform.system()
        os_release = platform.release()
        kernel = platform.version()
        arch = platform.machine()

        summary = (
            f"Bot: {bot_nick} | "
            f"Python: {python_version} | "
            f"Limnoria: {limnoria_version} | "
            f"OS: {os_name} {os_release} | "
            f"Kernel: {kernel} | "
            f"Arch: {arch}"
        )

        irc.reply(summary)

    # ----------------------------------------------------------------------
    @wrap(["channel", "text"])
    def say(self, irc, msg, args, channel, text):
        """say <channel> <text>

        Sends a message to a channel.
        """
        out = ircmsgs.privmsg(channel, text)

        # Tag outgoing message as owner so Limnoria does not rewrite or block it
        out.tag("identified", True)
        out.tag("authenticated", True)
        out.tag("account", "owner")  # type: ignore[arg-type]

        # Queue the message for actual network send
        irc.queueMsg(out)

        # Acknowledge the command
        irc.replySuccess()

    # ----------------------------------------------------------------------
    @wrap([])
    def info(self, irc, msg, args):
        """Shows information about the LocalControl plugin."""
        irc.reply("LocalControl provides a UNIX socket for local command execution.")


Class = LocalControl

# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
