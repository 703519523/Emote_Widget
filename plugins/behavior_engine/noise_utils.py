import random
import math

class SimpleNoise:
    """
    一个极简的 1D 柏林噪声实现，用于生成平滑的随机变化数值。
    不需要外部依赖 (numpy/scipy)。
    """
    def __init__(self, seed: int | None = None):
        if seed is None:
            seed = random.randint(0, 10000)
        self.perm = list(range(256))
        random.seed(seed)
        random.shuffle(self.perm)
        self.perm += self.perm # Double it for easier overflow handling
        
    def noise(self, x: float) -> float:
        """
        计算 1D 噪声值。
        
        Args:
            x (float): 输入坐标 (通常是时间)
            
        Returns:
            float: 范围在 [-1.0, 1.0] 之间的平滑噪声值
        """
        # Determine grid cell coordinates
        x0 = int(math.floor(x)) & 255
        x1 = (x0 + 1) & 255
        
        # Relative x within cell
        tx = x - math.floor(x)
        
        # Compute fade curves for x (Ease function)
        # 6t^5 - 15t^4 + 10t^3
        u = tx * tx * tx * (tx * (tx * 6 - 15) + 10)
        
        # Hash coordinates of the 2 corners
        # (For 1D, corners are just left and right endpoints)
        a = self.perm[x0]
        b = self.perm[x1]
        
        # Gradient values
        # We need to map hash value to a gradient.
        # In 1D, gradients are just 1 or -1.
        # We can simulate this by taking (hash & 1) and mapping 0->1, 1->-1
        grad_a = 1 if (a & 1) == 0 else -1
        grad_b = 1 if (b & 1) == 0 else -1
        
        # Add blend
        # Dot product of gradient and distance vector
        val_a = grad_a * tx
        val_b = grad_b * (tx - 1)
        
        # Linear interpolation
        return (1 - u) * val_a + u * val_b

class EmotionalWalker:
    """
    情感空间游走器。
    维护两个维度的噪声发生器，模拟情感在 Valence-Arousal 空间中的游走。
    """
    def __init__(self):
        self.noise_valence = SimpleNoise() # X轴: 情绪效价 (负面 <-> 正面)
        self.noise_arousal = SimpleNoise() # Y轴: 唤醒度 (困倦 <-> 兴奋)
        self.time_offset = 0.0
        
    def step(self, delta_time: float, speed: float = 0.1) -> tuple[float, float]:
        """
        前进一步。
        
        Args:
            delta_time (float): 时间增量
            speed (float): 游走速度，越小越平滑
            
        Returns:
            (valence, arousal): 范围通常在 [-0.8, 0.8] 之间
        """
        self.time_offset += delta_time * speed
        
        # 使用不同的偏移量避免两个轴同步
        v = self.noise_valence.noise(self.time_offset)
        a = self.noise_arousal.noise(self.time_offset + 100.0)
        
        # 噪声原始输出大约在 [-0.5, 0.5] 之间，稍微放大一点填满空间
        return (v * 1.5, a * 1.5)
