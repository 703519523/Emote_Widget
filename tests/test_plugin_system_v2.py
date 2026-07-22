import unittest

from emote_widget.core.event_bus import EventBus, event_bus
from emote_widget.core.middleware import Middleware, MiddlewareManager


class _AppendMiddleware(Middleware):
    def __init__(self, name, trace):
        self.name = name
        self.trace = trace

    def process(self, data, next):
        self.trace.append(f"before:{self.name}")
        result = next(data + [self.name])
        self.trace.append(f"after:{self.name}")
        return result


class _StopMiddleware(Middleware):
    def process(self, data, next):
        return {"stopped": True, "data": data}


class _MarkerMiddleware(Middleware):
    def process(self, data, next):
        data.append("marker")
        return next(data)


class PluginSystemV2Tests(unittest.TestCase):
    def tearDown(self):
        event_bus.clear()
        MiddlewareManager.clear_all()

    def test_event_bus_is_singleton_and_dispatches_events(self):
        self.assertIs(EventBus(), event_bus)
        received = []

        event_bus.on("test.event", received.append)
        event_bus.emit("test.event", {"value": 1})

        self.assertEqual(received, [{"value": 1}])

        event_bus.off("test.event", received.append)
        event_bus.emit("test.event", {"value": 2})
        self.assertEqual(received, [{"value": 1}])

    def test_middleware_wraps_terminal_in_registration_order(self):
        trace = []
        chain = MiddlewareManager.get_chain("test.chain")
        chain.use(_AppendMiddleware("one", trace))
        chain.use(_AppendMiddleware("two", trace))

        result = chain.execute([], terminal=lambda data: {"data": data})

        self.assertEqual(result, {"data": ["one", "two"]})
        self.assertEqual(
            trace,
            ["before:one", "before:two", "after:two", "after:one"],
        )

    def test_middleware_can_short_circuit_pipeline(self):
        chain = MiddlewareManager.get_chain("test.stop")
        chain.use(_StopMiddleware())

        result = chain.execute("input", terminal=lambda _: self.fail("terminal called"))

        self.assertEqual(result, {"stopped": True, "data": "input"})

    def test_middleware_can_remove_only_its_own_registration(self):
        chain = MiddlewareManager.get_chain("test.cleanup")
        first = _MarkerMiddleware()
        second = _MarkerMiddleware()
        chain.use(first)
        chain.use(second)

        chain.remove(first)

        result = chain.execute([])
        self.assertEqual(result, ["marker"])
        self.assertEqual(chain.middlewares, [second])

    def test_plugin_cleanup_preserves_other_plugins_middleware(self):
        from plugins.psb_decryption.main import PsbDecryptionPlugin

        chain = MiddlewareManager.get_chain("psb.normalize")
        marker = _MarkerMiddleware()
        chain.use(marker)
        plugin = PsbDecryptionPlugin()
        plugin.initialize()

        plugin.cleanup()

        self.assertEqual(chain.middlewares, [marker])


if __name__ == "__main__":
    unittest.main()