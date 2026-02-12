from typing import Any, TypeVar
from emote_widget.core.controller import EmoteController

T = TypeVar('T', bound=EmoteController)

class ControllerProxy(EmoteController):
    """
    [安全代理]
    
    作用：
    1. 拦截对私有属性（_开头）的访问。
    2. 仅暴露公共业务 API 给用户。
    3. 配合 Type Hinting 实现安全的 IDE 补全体验。
    """
    _impl: EmoteController
    
    def __init__(self, controller: EmoteController):
        # 保存真实控制器的引用
        # 使用 super().__setattr__ 防止递归调用自身的 __setattr__ (如果以后要加 setter)
        super().__setattr__('_impl', controller)

    def __getattr__(self, name: str):
        """当用户访问 proxy.xxx 时触发"""
        
        # 1. 禁止访问下划线开头的私有成员
        if name.startswith('_'):
            raise AttributeError(f"Access denied: '{name}' is private.")

        # 2. 获取真实属性
        if not hasattr(self._impl, name):
            raise AttributeError(f"'{type(self._impl).__name__}' has no attribute '{name}'")
            
        attr = getattr(self._impl, name)
        return attr

    def __setattr__(self, name: str, value: Any):
        """禁止外部修改 Controller 的属性 (只读保护)"""
        # 通常 Controller 的状态应该通过方法调用来改变
        if name.startswith('_'):
             raise AttributeError(f"Access denied: Cannot set private attribute '{name}'.")
        
        # 转发设置给实现对象
        setattr(self._impl, name, value)

    def __dir__(self):
        """定制 dir() 结果，过滤掉私有属性"""
        all_attrs = dir(self._impl)
        return [x for x in all_attrs if not x.startswith('_')]