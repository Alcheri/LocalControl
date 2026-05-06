###
# Copyright (c) 2026, Barry KW Suridge
# All rights reserved.
#
#
###

from supybot import conf, registry

try:
    from supybot.i18n import PluginInternationalization

    _ = PluginInternationalization("LocalControl")
except:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x: x


def configure(advanced):
    # This will be called by supybot to configure this module.  advanced is
    # a bool that specifies whether the user identified themself as an advanced
    # user or not.  You should effect your configuration by manipulating the
    # registry as appropriate.
    from supybot.questions import expect, anything, something, yn

    conf.registerPlugin("LocalControl", True)


LocalControl = conf.registerPlugin("LocalControl")
conf.registerGlobalValue(
    LocalControl,
    "socketRequestLogging",
    registry.Boolean(
        True,
        _("""Whether LocalControl writes one log line per socket request."""),
    ),
)
conf.registerGlobalValue(
    LocalControl,
    "socketRequestFullCommandLogging",
    registry.Boolean(
        False,
        _("""Whether LocalControl logs full socket command text after redaction."""),
    ),
)
conf.registerGlobalValue(
    LocalControl,
    "tcpListenerEnabled",
    registry.Boolean(
        False,
        _("""Whether LocalControl also listens on TCP for local testing."""),
    ),
)
conf.registerGlobalValue(
    LocalControl,
    "tcpListenHost",
    registry.String(
        "127.0.0.1",
        _("""Host address for the optional TCP listener."""),
    ),
)
conf.registerGlobalValue(
    LocalControl,
    "tcpListenPort",
    registry.PositiveInteger(
        8023,
        _("""Port for the optional TCP listener."""),
    ),
)
conf.registerGlobalValue(
    LocalControl,
    "tcpAllowRemote",
    registry.Boolean(
        False,
        _("""Whether the optional TCP listener may bind to non-loopback hosts."""),
    ),
)


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
