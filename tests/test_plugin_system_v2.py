import unittest
import inspect
import json
import os
import tempfile

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

    def test_plugin_loader_worker_finishes_by_stopping_its_thread(self):
        from emote_widget.core.controller import EmoteController

        source = inspect.getsource(EmoteController.__init__)
        self.assertIn(
            "self._plugin_loader_worker.finished.connect(self._plugin_loader_thread.quit)",
            source,
        )

    def test_plugin_state_defaults_to_enabled_and_persists_disabled_modules(self):
        from emote_widget.core.plugin_system import PluginStateStore

        with tempfile.TemporaryDirectory() as plugin_dir:
            state = PluginStateStore(plugin_dir)
            self.assertTrue(state.is_enabled("demo_plugin"))

            state.set_enabled("demo_plugin", False)

            reloaded = PluginStateStore(plugin_dir)
            self.assertFalse(reloaded.is_enabled("demo_plugin"))
            with open(os.path.join(plugin_dir, ".plugin_state.json"), encoding="utf-8") as file:
                self.assertEqual(
                    json.load(file),
                    {"disabled_plugins": ["demo_plugin"]},
                )

    def test_plugin_loader_scan_excludes_disabled_modules(self):
        from emote_widget.core.plugin_system import PluginLoaderWorker, PluginStateStore

        with tempfile.TemporaryDirectory() as plugin_dir:
            open(os.path.join(plugin_dir, "enabled.py"), "w", encoding="utf-8").close()
            open(os.path.join(plugin_dir, "disabled.py"), "w", encoding="utf-8").close()
            state = PluginStateStore(plugin_dir)
            state.set_enabled("disabled", False)
            worker = PluginLoaderWorker(plugin_dir, state_store=state)

            worker.scan_for_plugin_modules()

            self.assertEqual(worker.modules_to_load, ("enabled",))

    def test_rescan_replaces_stale_module_list_after_state_changes(self):
        from emote_widget.core.plugin_system import PluginLoaderWorker, PluginStateStore

        with tempfile.TemporaryDirectory() as plugin_dir:
            open(os.path.join(plugin_dir, "demo.py"), "w", encoding="utf-8").close()
            state = PluginStateStore(plugin_dir)
            worker = PluginLoaderWorker(plugin_dir, state_store=state)
            worker.scan_for_plugin_modules()
            self.assertEqual(worker.modules_to_load, ("demo",))

            state.set_enabled("demo", False)
            worker.scan_for_plugin_modules()

            self.assertEqual(worker.modules_to_load, ())

    def test_plugin_accessor_cleanup_and_clear_removes_runtime_plugins(self):
        from emote_widget.core.plugin_system import PluginAccessor

        class RuntimePlugin:
            cleaned = False

            def get_name(self):
                return "runtime_plugin"

            def cleanup(self):
                self.cleaned = True

        plugin = RuntimePlugin()
        plugins = PluginAccessor()
        plugins.register(plugin)

        plugins.cleanup_all(clear=True)

        self.assertTrue(plugin.cleaned)
        self.assertIsNone(plugins.get("runtime_plugin"))

    def test_controller_exposes_persistent_state_and_explicit_reload_api(self):
        from emote_widget.core.controller import EmoteController

        self.assertTrue(callable(getattr(EmoteController, "set_plugin_enabled", None)))
        self.assertTrue(callable(getattr(EmoteController, "is_plugin_enabled", None)))
        self.assertTrue(callable(getattr(EmoteController, "reload_plugins", None)))

    def test_corrupt_plugin_state_fails_open_without_disabling_plugins(self):
        from emote_widget.core.plugin_system import PluginStateStore

        with tempfile.TemporaryDirectory() as plugin_dir:
            with open(os.path.join(plugin_dir, ".plugin_state.json"), "w", encoding="utf-8") as file:
                file.write("not-json")

            self.assertTrue(PluginStateStore(plugin_dir).is_enabled("demo"))

    def test_controller_reload_rejects_concurrent_load_without_cleanup(self):
        from emote_widget.core.controller import EmoteController

        class RunningThread:
            def isRunning(self):
                return True

        class Plugins:
            cleanup_called = False

            def cleanup_all(self, clear=False):
                self.cleanup_called = True

        controller = EmoteController.__new__(EmoteController)
        controller._plugin_loader_thread = RunningThread()
        controller.plugins = Plugins()

        self.assertFalse(controller.reload_plugins())
        self.assertFalse(controller.plugins.cleanup_called)


if __name__ == "__main__":
    unittest.main()