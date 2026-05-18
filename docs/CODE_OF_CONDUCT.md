# Code of Conduct

## Purpose

LocalControl provides a local command path for Limnoria bots. Access to its UNIX
socket or optional TCP listener is equivalent to owner-level bot access, so this
project has a stronger security and operator-safety focus than a normal utility
plugin.

This Code of Conduct sets expectations for respectful community behaviour and
responsible handling of LocalControl's control surface.

## Community Standards

Contributors, operators, and users are expected to:

- Treat other people with respect and patience.
- Give and accept technical feedback constructively.
- Avoid harassment, intimidation, personal attacks, and discriminatory language.
- Avoid publishing private information without explicit permission.
- Keep discussion focused on improving the plugin and its safe operation.

Unacceptable behaviour includes abuse, harassment, sustained disruption, and
conduct that would reasonably make other people feel unsafe or unwelcome.

## Responsible Control Access

LocalControl must be treated as an owner-control channel, not as a general
remote administration interface. Contributors and operators should assume that
anyone who can connect to the socket or enabled listener can issue powerful bot
commands.

Responsible use includes:

- keeping socket paths and parent directories restricted to trusted local users;
- preserving owner-only socket permissions;
- keeping the TCP listener disabled unless it is deliberately needed;
- keeping TCP loopback-only unless the deployment is explicitly isolated;
- avoiding command examples that encourage exposing owner-level access.

Changes that broaden access should explain the operational need, document the
risk, and include tests or review notes for the relevant safeguard.

## Security-Sensitive Contributions

Contributors should preserve safeguards that reduce accidental control-channel
exposure, including:

- hostmask-based owner mapping through Limnoria;
- owner-only socket mode;
- bounded client timeouts;
- serialised dispatch where needed for stable bot interaction;
- minimal request logging by default;
- redaction when full command logging is explicitly enabled.

Do not add behaviour that logs secrets, passwords, tokens, private command text,
or sensitive bot output by default.

## Privacy And Logs

LocalControl can send commands and receive replies that may include private bot
state, channel data, hostmasks, configuration values, or operational details.
Operators should keep logs restricted and enable full command logging only for
short, deliberate debugging sessions.

If a report includes logs, redact secrets, credentials, private hostmasks, and
unrelated channel content before sharing it publicly.

## Operator Responsibilities

Operators are responsible for configuring LocalControl appropriately for their
machine and bot account. This includes filesystem permissions, synthetic
hostmask setup, TCP listener settings, SSH or wrapper access, and log handling.

Operational guidance belongs in the README and security reports belong in the
[Security Policy](SECURITY.md). General conduct concerns may be reported to
@Alcheri on GitHub.

## Enforcement

Project maintainers may remove comments, reject contributions, close issues,
block users, or decline support when behaviour conflicts with this Code of
Conduct or creates avoidable safety risk.

Enforcement should be proportionate, documented where practical, and mindful of
the privacy and security of people reporting concerns.

## Attribution

The community standards and enforcement structure are informed by the
[Contributor Covenant](https://www.contributor-covenant.org/), version 2.0, and
adapted for a security-sensitive Limnoria control plugin.
