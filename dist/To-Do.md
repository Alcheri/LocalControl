# GUI Beta Roadmap

## Eggdrop

Separate the transport and session model later, because Eggdrop is interactive Telnet/partyline rather than LocalControl command/reply.

Pragmatic first step:

- Add a `ttk.Notebook`
- Put the current LocalControl command UI in a LocalControl tab
- Move theme and connection fields into a Settings tab
- Leave output visible on the LocalControl tab

That keeps the current workflow intact but stops the top of the GUI from becoming crowded as SSH and profiles grow.

## Also supported

- Windows: `%APPDATA%\LocalControl GUI\botctl_gui.json`
- Override: `BOT_CONTROL_GUI_SETTINGS=/path/to/file.json`

## Socket Read Follow-up

~~The GUI freeze risk is fixed by background transport threads and read timeouts.~~

~~Remaining cleanup: make LocalControl server-side command reads explicitly line-based instead of relying on a single `recv(4096)`, and consider matching `botctl` reply reads to the GUI read loop.~~

## Error Logging Follow-up

- ~~Add optional GUI diagnostic logging to a `botctl_gui.json`-controlled location, disabled or minimal by default.~~
- ~~Log transport type, endpoint label, command summary, timestamp, duration, and error class/message.~~
- ~~Do not log full command text by default; redact sensitive command arguments if full logging is ever added.~~
- Keep plugin-side logging quiet and structured: status, request id, duration, reply count, command summary.
- Consider a "Copy diagnostics" action in the GUI for the last failed request.

## Beta Binary Testing

### Normal Use

- [x] Launch, close, relaunch
- [x] Settings persist
- [x] Window geometry persists
- [x] Command history persists

### Transport Failures

- [x] Missing UNIX socket (Linux only)
- [x] TCP listener disabled
- [x] Wrong TCP port
- [x] SSH host unreachable
- [x] SSH unknown host
- [x] SSH auth failure

### Command Behaviour

- [x] Normal short reply
- [x] Long reply
- [ ] No reply
- [x] Plugin error reply
- [x] Repeated commands

## Windows GUI UI Fine Tuning

- ~~Remove the editable SSH client field.~~
- ~~Use native Windows OpenSSH (`ssh`) internally for SSH mode.~~
- ~~Add concise Windows SSH mode helper text:~~

  > ~~Windows OpenSSH needs a key or ssh-agent identity. Password prompts are not available in the GUI.~~

- ~~Keep the GUI 100% free of WSL references and WSL launcher support.~~
- Shorten SSH authentication failure output so it is clear without being noisy.
- Consider a separate "Test connection" action so users can verify OpenSSH authentication without sending `sysinfo`.
- ~~Add server settings drop-down menus for SSH user and SSH host, storing saved values in `botctl_gui.json`.~~
- ~~Add right-click mouse menu options for editable fields in Settings.~~
- ~~Reconsider current fonts for the UI.~~
- ~~Consider coloured command headers/output styling so commands stand out.~~
- ~~Remove "UNIX socket: missing" and "LocalControl via UNIX: inactive" from the Windows LocalControl UI/status output.~~

## Linux GUI UI Fine Tuning

- ~~Keep the editable SSH client field.~~
- ~~Keep the default or recommended SSH command as `ssh`.~~
- ~~Add server settings drop-down menus for SSH user and SSH host, storing saved values in `botctl_gui.json`.~~
- ~~Add right-click mouse menu options for editable fields in Settings.~~
- ~~Consider coloured command headers/output styling so commands stand out.~~

## Both UIs

- Use `ttk.Notebook` in both GUI apps to keep LocalControl commands, Settings, and future sections separated.
- ~~Add an in-app Help button or Help tab covering transports, Windows OpenSSH keys, diagnostics, settings paths, and basic troubleshooting.~~
- Think of a better name for the GUI apps.
