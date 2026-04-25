###
# Copyright (c) 2026, Barry KW Suridge
# All rights reserved.
#
#
###

import unittest

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


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
