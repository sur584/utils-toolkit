"""
微信视频号视频解密模块
实现 ISAAC 流密码解密算法
"""

import struct


class ISAAC:
    """ISAAC 随机数生成器"""

    def __init__(self, seed: int):
        self.count = 0
        self.rsl = [0] * 256
        self.mem = [0] * 256
        self.a = 0
        self.b = 0
        self.c = 0
        self._init(seed)

    def _init(self, seed: int):
        """初始化 ISAAC 状态"""
        # 设置种子
        self.mem[0] = seed
        for i in range(1, 256):
            self.mem[i] = (self.mem[i - 1] * 1103515245 + 12345) & 0xFFFFFFFF

        # 混合状态
        for _ in range(4):
            self._mix()

        # 填充随机数缓冲区
        for i in range(0, 256, 8):
            self.a = (self.a + self.mem[i]) & 0xFFFFFFFF
            self.b = (self.b + self.mem[i + 1]) & 0xFFFFFFFF
            self.c = (self.c + self.mem[i + 2]) & 0xFFFFFFFF
            self._isaac()
            for j in range(8):
                self.mem[i + j] = (self.mem[i + j] + self.rsl[j]) & 0xFFFFFFFF

        self._isaac()
        self.count = 256

    def _mix(self):
        """混合操作"""
        self.a = self.a ^ (self.a << 13) & 0xFFFFFFFF
        self.a = self.a ^ (self.a >> 6) & 0xFFFFFFFF
        self.a = self.a ^ (self.a << 2) & 0xFFFFFFFF
        self.b = self.b ^ (self.b << 2) & 0xFFFFFFFF
        self.b = self.b ^ (self.b >> 16) & 0xFFFFFFFF
        self.b = self.b ^ (self.a << 10) & 0xFFFFFFFF
        self.c = self.c ^ (self.c >> 11) & 0xFFFFFFFF
        self.c = self.c ^ (self.c << 7) & 0xFFFFFFFF
        self.c = self.c ^ (self.a << 13) & 0xFFFFFFFF
        self.c = self.c ^ (self.c >> 18) & 0xFFFFFFFF
        self.c = self.c ^ (self.b << 3) & 0xFFFFFFFF
        self.c = self.c ^ (self.c >> 10) & 0xFFFFFFFF

    def _isaac(self):
        """生成一组随机数"""
        self.c = (self.c + 1) & 0xFFFFFFFF
        self.b = (self.b + self.c) & 0xFFFFFFFF

        for i in range(256):
            x = self.mem[i]
            match i & 3:
                case 0:
                    self.a = (self.a ^ (self.a << 13)) & 0xFFFFFFFF
                case 1:
                    self.a = (self.a ^ (self.a >> 6)) & 0xFFFFFFFF
                case 2:
                    self.a = (self.a ^ (self.a << 2)) & 0xFFFFFFFF
                case 3:
                    self.a = (self.a ^ (self.a >> 16)) & 0xFFFFFFFF

            self.a = (self.mem[(i + 128) & 0xFF] + self.a) & 0xFFFFFFFF
            y = (self.mem[(self.rsl[i] >> 2) & 0xFF] + self.a + self.b) & 0xFFFFFFFF
            self.mem[i] = y
            self.b = (self.mem[(y >> 10) & 0xFF] + x) & 0xFFFFFFFF
            self.rsl[i] = self.b

    def random(self) -> int:
        """返回一个 32 位随机数"""
        if self.count == 0:
            self._isaac()
            self.count = 256
        self.count -= 1
        return self.rsl[self.count]


def decrypt_isaac(data: bytes, key: int) -> bytes:
    """
    使用 ISAAC 流密码解密视频数据

    Args:
        data: 加密的视频数据
        key: 解密密钥

    Returns:
        解密后的视频数据
    """
    if not data:
        return data

    ctx = ISAAC(key)
    result = bytearray(len(data))

    for i in range(len(data)):
        # 生成密钥流
        if i % 4 == 0:
            key_stream = ctx.random()
        # 逐字节异或
        result[i] = data[i] ^ ((key_stream >> (8 * (i % 4))) & 0xFF)

    return bytes(result)
