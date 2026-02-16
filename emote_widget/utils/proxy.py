import functools
import traceback
import inspect
from PySide6.QtCore import QObject, Slot
from emote_widget.utils.logger import plugin_logger as logger

def wrap_as_qml_slot(func):
    """
    检查方法是否为 Slot，如果不是，则将其包装为安全的 QML Slot。
    
    功能:
    1. 检查是否已有 __pyside_signals__ (即是否已经是 Slot)。
    2. 如果不是，创建一个接受 (*args, **kwargs) 的包装器。
    3. 包装器使用 @Slot(result="QVariant") 装饰。
    4. 包装器包含 try...except 块，通过 py_api.on_js_error 报告错误。
    """
    if getattr(func, "__pyside_signals__", None) or getattr(func, "_slots", None):
        return func
    
    # 获取函数名用于日志
    func_name = getattr(func, "__name__", "unknown_method")

    @Slot(result="QVariant")
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = f"Error in plugin method '{func_name}': {str(e)}"
            stack = traceback.format_exc()
            logger.error(f"{error_msg}\n{stack}")
            
            # 尝试查找 controller 并报告给前端
            # 假设 args[0] 是 self (插件实例)，且插件实例有 controller 属性
            if args:
                instance = args[0]
                controller = getattr(instance, "controller", None)
                if controller:
                    # 尝试调用 bridge 的 on_js_error
                    # controller._bridge 是 private，但 controller 有 _safe_run
                    # 我们构造一段 JS 调用
                    
                    # 转义字符串
                    import json
                    safe_msg = json.dumps(error_msg)
                    safe_stack = json.dumps(stack)
                    
                    # 检查 bridge 是否存在，通常注册为 py_api
                    js_code = f"if(typeof py_api !== 'undefined' && py_api.on_js_error) py_api.on_js_error({safe_msg}, {safe_stack});"
                    
                    # 通过 controller 执行
                    if hasattr(controller, "_safe_run"):
                         controller._safe_run(js_code)
                    elif hasattr(controller, "view_adapter"):
                         controller.view_adapter.run_javascript(js_code)

            return None # 返回 None 给 JS

    return wrapper

class SafePluginQmlProxy(QObject):
    """
    继承自 QObject 的动态代理，确保所有方法调用都是安全的 Slot。
    用于在 QML 环境中安全地暴露插件。
    """
    def __init__(self, target_plugin):
        super().__init__()
        self._target = target_plugin
        # 动态将 target 的方法绑定到 self 上，并确保是 Slot
        # 注意：QML 访问 QObject 的方法需要这些方法在 QObject 的元对象中。
        # 仅仅在实例上 setattr 可能不够，因为 PySide 的元对象是在类定义时构建的。
        # 为了让 QML 看到这些 Slot，我们需要动态构建一个类，或者使用 getattr 转发？
        # 但 QObject 没有通用的 getattr for QML calls.
        
        # 鉴于 PySide/Qt 机制，要在运行时动态暴露方法给 QML，通常比较复杂。
        # 但既然 Step B 已经对插件类进行了 "Sanitizing" (添加 Slot)，
        # 那么插件原本的方法已经是 Slot 了。
        # 如果插件本身是 QObject，我们可以直接返回插件。
        # 如果插件不是 QObject (IEmotePlugin 继承 ABC)，我们需要这个 Proxy。
        
        # 为了让 Proxy 拥有对应的方法，我们需要在 Proxy *Class* 上定义这些 Slot。
        # 由于 Python 是动态的，我们可以为每个 Plugin 动态创建一个 Proxy Class。
        
        # 但是，我们必须在 __init__ 中做不到修改类结构让 Qt 知道。
        # 我们需要在实例化 Proxy 之前，或者使用特殊的元类。
        pass

def create_safe_proxy(plugin_instance):
    """
    为插件实例创建 SafePluginQmlProxy。
    动态生成一个继承自 QObject 的类，该类包含插件所有公共方法的 Slot 包装。
    """
    plugin_cls = plugin_instance.__class__
    # 收集公共方法
    methods = {}
    
    for name, member in inspect.getmembers(plugin_instance):
        if name.startswith("_"): continue
        if not callable(member): continue
        
        # 既然 Step B 已经 wrap 了 Slot，我们这里只需要转发。
        # 但我们需要在 Proxy 类上定义对应的 Slot。
        
        # 定义转发函数
        # 注意闭包捕获 name
        def make_forwarder(method_name, original_method):
             # 检查原始方法是否已经是 Slot
             # Step B 应该已经处理了，但为了保险，我们这里再次 wrap?
             # 如果原始方法已经是 Slot，我们再 wrap 一层 Slot 也是可以的，或者直接调用。
             
             @Slot(result="QVariant")
             def forwarder(self, *args, **kwargs):
                 target_method = getattr(self._target, method_name)
                 return target_method(*args, **kwargs)
             return forwarder

        methods[name] = make_forwarder(name, member)

    # 创建动态类
    # 类名必须唯一，避免冲突? 其实无所谓，只要是类即可。
    proxy_cls_name = f"SafeProxy_{plugin_instance.get_name()}"
    
    # 继承 SafePluginQmlProxy (它继承 QObject)
    # 混入 methods
    proxy_cls = type(proxy_cls_name, (SafePluginQmlProxy,), methods)
    
    return proxy_cls(plugin_instance)
