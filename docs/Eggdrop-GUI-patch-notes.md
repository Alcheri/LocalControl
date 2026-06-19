# Eggdrop GUI Patch Notes

## Summary

This patch adds the first Eggdrop partyline workflow to the LocalControl GUI,
including direct Telnet connections and managed SSH tunnels.

## Added

- Added an `Eggdrop` tab to the LocalControl GUI.
- Renamed the visible control tabs to distinguish `Limnoria` command/reply
  control from `Eggdrop` partyline control.
- Renamed the shared LocalControl settings view to `Limnoria Settings`.
- Made the Windows LocalControl settings view SSH-first by hiding the local TCP
  host/port row; WSL-local Limnoria bots remain a Linux GUI workflow.
- Added local Pudding defaults:
  - host: `127.0.0.1`;
  - port: `3333`;
  - handle: `Barry`.
- Added a transport selector for Direct and SSH tunnel modes.
- Added editable Eggdrop Telnet host and port settings.
- Added editable SSH user, SSH host, SSH port, remote Telnet host, and remote
  Telnet port settings for tunnelled connections.
- Added Eggdrop drop-down history for SSH user, SSH host, and remote Telnet
  port settings.
- SSH tunnel mode starts an `ssh -N -L` tunnel before connecting to Eggdrop.
- Managed SSH tunnels are closed on Disconnect or GUI exit.
- Transport switching is disabled while connected.
- Added interactive Telnet session handling for Eggdrop partyline access.
- Added manual, prompt-aware login:
  - handle prompts focus/select the handle field;
  - password prompts focus the masked password field;
  - successful partyline login focuses the Eggdrop input field.
- Added Enter-key sending for handle, password, and Eggdrop input fields.
- Added transcript output for Eggdrop session traffic.
- Added Copy/Clear actions for the Eggdrop transcript.
- Added Up/Down input history navigation for Eggdrop partyline commands.
- Persisted Eggdrop input history in GUI settings, capped at 50 entries.

## Security

- Eggdrop passwords are not saved.
- Password entry uses a masked field.
- Sent password lines are redacted in the transcript.
- Telnet-echoed password text is redacted in the transcript.
- Pending password redaction tokens are cleared on disconnect and before new
  connection attempts.
- Eggdrop diagnostic logging records connection/action metadata only.
- Managed SSH tunnel start/failure metadata can be written to diagnostics.
- SSH tunnel connection waits report early tunnel exits separately from local
  port timeouts.
- Diagnostics do not log Eggdrop passwords or full transcript content.
- Sensitive-looking Eggdrop input lines are excluded from persisted history.

## Fixed During Testing

- Fixed Telnet negotiation bytes showing as unreadable characters in the
  transcript.
- Fixed password echo leakage in the transcript.
- Fixed stale password redaction tokens persisting across reconnects.
- Fixed duplicate `Disconnected` output when using the Disconnect button.

## Validation

- Unix `LocalControl-GUI` was rebuilt and tested against local Pudding.
- Windows `LocalControl-GUI.exe` was rebuilt and tested against local Pudding.
- Windows native OpenSSH key authentication was configured and tested for
  private remote Eggdrop accounts.
- Linux and Windows GUI validation passed for local Pudding and private remote
  Eggdrop settings entered through the UI.
- Windows validation passed for:
  - application launch;
  - Eggdrop tab rendering;
  - prompt-aware focus changes;
  - password redaction;
  - Up/Down input history;
  - single disconnect output.
- LocalControl plugin tests passed: `12 passed`.
- GUI source formatting passed with Black.
- Focused Bandit security check passed for `tools/botctl_gui.py`.

## Deferred

- Remote Eggdrop listener-port instability needs separate investigation.
- SSH remains an external tunnel transport, not a native Eggdrop partyline
  listener.
- TLS/SSL Telnet remains the Eggdrop-native encrypted direct-listener option.
- Saved Eggdrop passwords remain out of scope unless OS credential storage is
  deliberately added later.
