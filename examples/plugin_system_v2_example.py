"""
插件系统 v2 使用示例

展示如何使用 EventBus 和 Middleware 系统创建强大的插件。
"""

from emote_widget.core.event_bus import event_bus
from emote_widget.core.middleware import Middleware, MiddlewareManager
from emote_widget.core.plugin_interface import IEmotePlugin


# ============================================================================
# 示例 1: 使用 EventBus 监听生命周期事件
# ============================================================================

class EventListenerPlugin(IEmotePlugin):
    """演示如何监听事件的插件"""
    
    def get_name(self) -> str:
        return "event_listener_example"
    
    def get_description(self) -> str:
        return "演示 EventBus 事件监听"
    
    def initialize(self):
        # 订阅模型加载事件
        event_bus.on("model.loaded", self.on_model_loaded)
        event_bus.on("player.ready", self.on_player_ready)
        event_bus.on("animation.play", self.on_animation_play)
        
        self.logger.info("事件监听插件已初始化")
    
    def on_model_loaded(self, data):
        """当模型加载完成时触发"""
        self.logger.info(f"模型已加载: {data.get('path')}")
    
    def on_player_ready(self, data):
        """当播放器就绪时触发"""
        self.logger.info(f"播放器就绪，动画数: {len(data.get('timelines', []))}")
    
    def on_animation_play(self, data):
        """当开始播放动画时触发"""
        self.logger.info(f"播放动画: {data.get('name')}")
    
    def cleanup(self):
        # 清理：取消所有订阅
        event_bus.off("model.loaded", self.on_model_loaded)
        event_bus.off("player.ready", self.on_player_ready)
        event_bus.off("animation.play", self.on_animation_play)


# ============================================================================
# 示例 2: 使用 Middleware 干预数据流水线
# ============================================================================

class LoggingMiddleware(Middleware):
    """记录所有通过的数据"""
    
    def process(self, data, next):
        print(f"[LoggingMiddleware] 数据进入: {type(data)}")
        result = next(data)  # 继续流水线
        print(f"[LoggingMiddleware] 数据输出: {type(result)}")
        return result


class ValidationMiddleware(Middleware):
    """验证数据有效性"""
    
    def process(self, data, next):
        # 检查数据
        if not isinstance(data, dict):
            raise ValueError("数据必须是字典类型")
        
        if "path" not in data:
            raise ValueError("数据缺少 'path' 字段")
        
        # 验证通过，继续
        return next(data)


class TransformMiddleware(Middleware):
    """转换数据格式"""
    
    def process(self, data, next):
        # 添加时间戳
        import time
        data["timestamp"] = time.time()
        data["processed"] = True
        
        # 继续流水线
        return next(data)


class MiddlewarePlugin(IEmotePlugin):
    """演示如何使用中间件的插件"""
    
    def get_name(self) -> str:
        return "middleware_example"
    
    def get_description(self) -> str:
        return "演示 Middleware 数据流水线干预"
    
    def initialize(self):
        # 获取或创建中间件链
        chain = MiddlewareManager.get_chain("example.process")
        
        # 按顺序注册中间件
        chain.use(LoggingMiddleware())
        chain.use(ValidationMiddleware())
        chain.use(TransformMiddleware())
        
        self.logger.info("中间件插件已初始化")
    
    def cleanup(self):
        # 清理中间件链
        MiddlewareManager.clear_chain("example.process")


# ============================================================================
# 示例 3: 实际使用场景 - PSB 解密中间件
# ============================================================================

class PsbDecryptionMiddleware(Middleware):
    """PSB 解密中间件示例"""
    
    def process(self, data, next):
        path = data.get("path")
        
        # 检查是否需要解密
        if self._is_encrypted(path):
            print(f"[Decryption] 检测到加密 PSB: {path}")
            
            # 执行解密
            decrypted_path = self._decrypt(path)
            data["path"] = decrypted_path
            data["was_encrypted"] = True
            
            print(f"[Decryption] 解密完成: {decrypted_path}")
        
        # 继续流水线
        return next(data)
    
    def _is_encrypted(self, path):
        """检查文件是否加密（示例实现）"""
        # 实际实现会读取文件 header
        return False
    
    def _decrypt(self, path):
        """解密文件（示例实现）"""
        # 实际实现会调用 decrypt_psb
        return path


class PsbDecryptionPlugin(IEmotePlugin):
    """PSB 解密插件"""
    
    def get_name(self) -> str:
        return "psb_decryption"
    
    def get_description(self) -> str:
        return "自动解密加密的 PSB 文件"
    
    def initialize(self):
        # 注册到 PSB 处理流水线
        chain = MiddlewareManager.get_chain("psb.normalize")
        chain.use(PsbDecryptionMiddleware())
        
        self.logger.info("PSB 解密插件已启用")
    
    def cleanup(self):
        MiddlewareManager.clear_chain("psb.normalize")


# ============================================================================
# 示例 4: 组合使用 EventBus 和 Middleware
# ============================================================================

class HybridPlugin(IEmotePlugin):
    """同时使用事件和中间件的插件"""
    
    def get_name(self) -> str:
        return "hybrid_example"
    
    def get_description(self) -> str:
        return "组合使用 EventBus 和 Middleware"
    
    def initialize(self):
        # 1. 注册中间件干预数据流
        chain = MiddlewareManager.get_chain("parameter.transform")
        chain.use(ParameterTransformMiddleware())
        
        # 2. 监听事件进行通知
        event_bus.on("parameter.changed", self.on_parameter_changed)
        
        self.logger.info("混合插件已初始化")
    
    def on_parameter_changed(self, data):
        """参数改变时触发"""
        param_name = data.get("name")
        new_value = data.get("value")
        self.logger.info(f"参数已改变: {param_name} = {new_value}")
    
    def cleanup(self):
        MiddlewareManager.clear_chain("parameter.transform")
        event_bus.off("parameter.changed", self.on_parameter_changed)


class ParameterTransformMiddleware(Middleware):
    """参数转换中间件"""
    
    def process(self, data, next):
        # 在参数传递给核心前进行转换
        if "value" in data:
            # 例如：限制参数范围
            data["value"] = max(0.0, min(1.0, data["value"]))
        
        return next(data)


# ============================================================================
# 使用说明
# ============================================================================

if __name__ == "__main__":
    print("""
插件系统 v2 使用指南
==================

1. EventBus（事件总线）
   - 用途：监听生命周期事件和业务通知
   - 特点：单向广播，不改变数据流
   - 示例：监听 model.loaded, player.ready 等事件

2. Middleware（中间件）
   - 用途：在数据流水线中注入逻辑
   - 特点：可检查、修改、替换数据，支持中断流水线
   - 示例：PSB 解密、参数验证、格式转换

3. 组合使用
   - Middleware 处理数据转换
   - EventBus 发送处理结果通知
   - 实现完整的数据处理和事件通知流程

4. 插件开发最佳实践
   - 在 initialize() 中注册事件和中间件
   - 在 cleanup() 中清理资源
   - 使用 self.logger 记录日志
   - 处理异常，不要让插件崩溃
    """)
