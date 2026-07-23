import unittest
import inspect
import json
import os
import tempfile
from pathlib import Path

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

    def test_plugin_loader_instantiates_psb_package_plugin(self):
        from emote_widget.core.plugin_system import PluginLoaderWorker

        plugin_dir = Path(__file__).resolve().parents[1] / "plugins"
        worker = PluginLoaderWorker(str(plugin_dir))
        loaded = []
        worker.finished.connect(loaded.extend)

        worker.scan_for_plugin_modules()
        worker.run_loading()

        self.assertIn("psb_decryption", worker.modules_to_load)
        self.assertIn("psb_decryption", [plugin.get_name() for plugin in loaded])

    def test_example_plugin_demonstrates_safe_lifecycle_and_v2_extension_points(self):
        example_path = Path(__file__).resolve().parents[1] / "plugins" / "example" / "main.py"
        source = example_path.read_text(encoding="utf-8")

        self.assertIn('return "example"', source)
        self.assertIn("self.events.on(", source)
        self.assertIn("self.middleware.get_chain(", source)
        self.assertIn("player_ready.connect(", source)
        self.assertIn("猴子补丁", source)
        self.assertIn("不建议", source)

    def test_example_plugin_exports_example_class(self):
        init_path = Path(__file__).resolve().parents[1] / "plugins" / "example" / "__init__.py"
        source = init_path.read_text(encoding="utf-8")

        self.assertIn("ExamplePlugin", source)

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

    def test_controller_emits_structured_success_after_introspection(self):
        from emote_widget.core.controller import EmoteController

        class Adapter:
            def register_python_bridge(self, bridge, name):
                pass

            def run_javascript(self, script):
                pass

        with tempfile.TemporaryDirectory() as plugin_dir:
            controller = EmoteController(Adapter(), plugin_dir=plugin_dir)
            controller._requested_model_filename = "character.psb"
            controller._active_load_id = "load-1"
            controller._active_health_report = {"accepted": True}
            controller.get_variables = lambda callback: callback([])
            emitted = []
            controller.model_load_succeeded.connect(
                lambda path, report: emitted.append((path, report))
            )

            controller._perform_introspection(["idle"])

            self.assertEqual(
                emitted,
                [("character.psb", {"accepted": True})],
            )

    def test_rejected_model_keeps_previous_ready_model(self):
        from emote_widget.core import controller as controller_module
        from emote_widget.core.controller import EmoteController

        class Adapter:
            def register_python_bridge(self, bridge, name):
                pass

            def run_javascript(self, script):
                pass

        with tempfile.TemporaryDirectory() as plugin_dir:
            controller = EmoteController(Adapter(), plugin_dir=plugin_dir)
            controller.current_model_filename = "working.psb"
            controller._player_is_ready = True
            controller._model_state = "ready"
            controller.variable_map = {"old": {"name": "old"}}
            controller._active_load_id = "old-load"

            original_resolve = controller_module.resolve_resource_url
            controller_module.resolve_resource_url = lambda *_args: (_ for _ in ()).throw(
                controller_module.ResourceNormalizationError("bad PSB")
            )
            try:
                controller.load_model("broken.psb")
            finally:
                controller_module.resolve_resource_url = original_resolve

            self.assertTrue(controller._player_is_ready)
            self.assertEqual(controller._model_state, "ready")
            self.assertEqual(controller.current_model_filename, "working.psb")
            self.assertEqual(controller.variable_map, {"old": {"name": "old"}})

    def test_runtime_failure_restores_previous_ready_state(self):
        from emote_widget.core.controller import EmoteController

        class Adapter:
            def register_python_bridge(self, bridge, name):
                pass

            def run_javascript(self, script):
                pass

        with tempfile.TemporaryDirectory() as plugin_dir:
            controller = EmoteController(Adapter(), plugin_dir=plugin_dir)
            controller.current_model_filename = "working.psb"
            controller._player_is_ready = True
            controller._model_state = "ready"
            controller.variable_map = {"old": {"name": "old"}}
            controller._active_health_report = {"accepted": True}
            controller._active_load_id = "new-load"
            controller._previous_model_snapshot = {
                "filename": "working.psb",
                "player_ready": True,
                "state": "ready",
                "variable_map": controller.variable_map,
                "mouth_param_info": None,
                "health_report": {"accepted": True},
            }

            controller._fail_model_load(
                "broken.psb", "MODEL_RUNTIME_LOAD_FAILED", "bad runtime", False
            )

            self.assertTrue(controller._player_is_ready)
            self.assertEqual(controller._model_state, "ready")
            self.assertEqual(controller.current_model_filename, "working.psb")
            self.assertEqual(controller.variable_map, {"old": {"name": "old"}})

    def test_runtime_failure_does_not_discard_previous_js_player(self):
        renderer_path = Path(__file__).resolve().parents[1] / "emote_widget" / "web_frontend" / "js" / "core_renderer.js"
        source = renderer_path.read_text(encoding="utf-8")

        self.assertIn("if (!fatal) {", source)
        self.assertIn("window.modelLoadState = 'ready';", source)
        self.assertNotIn("window.emotePlayer = null;\n        if (window.py_api", source)

    def test_next_model_can_start_after_validation_failure(self):
        from emote_widget.core import controller as controller_module
        from emote_widget.core.controller import EmoteController

        class Adapter:
            def __init__(self):
                self.scripts = []

            def register_python_bridge(self, bridge, name):
                pass

            def run_javascript(self, script):
                self.scripts.append(script)

        adapter = Adapter()
        with tempfile.TemporaryDirectory() as plugin_dir:
            controller = EmoteController(adapter, plugin_dir=plugin_dir)
            controller.current_model_filename = "working.psb"
            controller._player_is_ready = True
            controller._model_state = "ready"

            original_resolve = controller_module.resolve_resource_url
            calls = iter([controller_module.ResourceNormalizationError("bad PSB"), "emote:///good.psb"])

            def resolve(*_args):
                result = next(calls)
                if isinstance(result, Exception):
                    raise result
                return result

            controller_module.resolve_resource_url = resolve
            try:
                controller.load_model("broken.psb")
                controller.load_model("good.psb")
            finally:
                controller_module.resolve_resource_url = original_resolve

            self.assertEqual(controller._model_state, "loading")
            self.assertTrue(any("loadNewModel" in script for script in adapter.scripts))

    def test_renderer_load_uses_candidate_player_before_commit(self):
        renderer_path = Path(__file__).resolve().parents[1] / "emote_widget" / "web_frontend" / "js" / "core_renderer.js"
        source = renderer_path.read_text(encoding="utf-8")

        self.assertIn("const previousPlayer = window.emotePlayer;", source)
        self.assertIn("let candidatePlayer = null;", source)
        self.assertIn("window.emotePlayer = candidatePlayer;", source)
        self.assertIn("window.emotePlayer = previousPlayer;", source)

    def test_renderer_releases_candidate_and_previous_player(self):
        renderer_path = Path(__file__).resolve().parents[1] / "emote_widget" / "web_frontend" / "js" / "core_renderer.js"
        source = renderer_path.read_text(encoding="utf-8")

        self.assertIn("candidatePlayer.destroy();", source)
        self.assertIn("previousPlayer.destroy();", source)

    def test_renderer_marks_player_commit_before_callback_can_fail(self):
        """桥接回调异常时，不能把已经提交的新 player 当成旧事务回滚。"""
        renderer_path = Path(__file__).resolve().parents[1] / "emote_widget" / "web_frontend" / "js" / "core_renderer.js"
        source = renderer_path.read_text(encoding="utf-8")

        self.assertIn("let playerCommitted = false;", source)
        self.assertIn("playerCommitted = true;", source)
        self.assertIn("if (playerCommitted) {", source)

    def test_emote_player_destroy_is_idempotent_and_release_uses_class_counter(self):
        renderer_path = Path(__file__).resolve().parents[1] / "emote_widget" / "web_frontend" / "driver" / "emoteplayer.js"
        source = renderer_path.read_text(encoding="utf-8")

        self.assertIn("if (this._destroyed) return;", source)
        self.assertIn("EmotePlayer.deviceRefCount", source)
        self.assertNotIn("sEmotePlayer.deviceRefCount", source)

    def test_emote_device_has_a_native_finish_lifecycle_method(self):
        renderer_path = Path(__file__).resolve().parents[1] / "emote_widget" / "web_frontend" / "driver" / "emoteplayer.js"
        source = renderer_path.read_text(encoding="utf-8")

        self.assertIn("destroy() {", source.split("class EmotePlayer", 1)[0])
        self.assertIn("EmoteDevice_Finish();", source)

    def test_webview_config_allows_memory_growth_for_large_models(self):
        html_path = Path(__file__).resolve().parents[1] / "emote_widget" / "web_frontend" / "pyside_webview.html"
        source = html_path.read_text(encoding="utf-8")

        self.assertIn("ALLOW_MEMORY_GROWTH: 1", source)

    def test_dialog_validation_waits_until_a_theme_has_loaded(self):
        dialog_path = Path(__file__).resolve().parents[1] / "emote_widget" / "web_frontend" / "js" / "dialog_system.js"
        source = dialog_path.read_text(encoding="utf-8")
        ensure_body = source.split("function ensureDialogElements() {", 1)[1].split(
            "// ==========================================================", 1
        )[0]

        loading_guard = ensure_body.index("if (!window.currentLoadedTheme) return false;")
        critical_log = ensure_body.index("Dialog theme structure invalid")
        self.assertLess(loading_guard, critical_log)

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

            def cleanup_all(self, clear: bool = False):
                self.cleanup_called = True

        controller = EmoteController.__new__(EmoteController)
        controller._plugin_loader_thread = RunningThread()  # pyright: ignore[reportAttributeAccessIssue, reportPrivateUsage]
        controller.plugins = Plugins()  # pyright: ignore[reportAttributeAccessIssue]

        self.assertFalse(controller.reload_plugins())
        self.assertFalse(controller.plugins.cleanup_called)

    def test_plugin_loader_lists_all_modules_with_enabled_state(self):
        from emote_widget.core.plugin_system import PluginLoaderWorker, PluginStateStore

        with tempfile.TemporaryDirectory() as plugin_dir:
            open(os.path.join(plugin_dir, "enabled.py"), "w", encoding="utf-8").close()
            disabled_dir = os.path.join(plugin_dir, "disabled")
            os.makedirs(disabled_dir)
            open(os.path.join(disabled_dir, "__init__.py"), "w", encoding="utf-8").close()
            state = PluginStateStore(plugin_dir)
            state.set_enabled("disabled", False)
            worker = PluginLoaderWorker(plugin_dir, state_store=state)

            self.assertEqual(
                worker.list_plugin_modules(),
                [
                    {"module": "disabled", "enabled": False},
                    {"module": "enabled", "enabled": True},
                ],
            )

    def test_builtin_plugins_expose_example_without_legacy_debug_module(self):
        from emote_widget.core.plugin_system import PluginLoaderWorker

        plugin_dir = str(Path(__file__).resolve().parents[1] / "plugins")
        modules = {
            item["module"] for item in PluginLoaderWorker(plugin_dir).list_plugin_modules()
        }

        self.assertIn("example", modules)
        self.assertNotIn("debug", modules)

    def test_qt_tester_plugin_tab_exposes_enable_and_reload_controls(self):
        tester_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "testers",
            "test_qt.py",
        )
        with open(tester_path, encoding="utf-8") as file:
            source = file.read()

        self.assertIn("self.plugin_state_list = QListWidget()", source)
        self.assertIn("self.reload_plugins_btn = QPushButton", source)
        self.assertIn("set_plugin_enabled", source)
        self.assertIn("reload_plugins()", source)


if __name__ == "__main__":
    unittest.main()