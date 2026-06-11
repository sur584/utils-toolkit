"""
微信视频号视频解密模块
实现 ISAAC-64 流密码解密算法（与 wx_channels_download 一致）
参考: https://github.com/Hanson/WechatSphDecrypt
"""

import struct

# ISAAC-64 常量：黄金比例
GOLDEN_RATIO = 0x9e3779b97f4a7c13
MASK64 = 0xFFFFFFFFFFFFFFFF


def _mix(v):
    """8-way parallel mixing function"""
    v[0] = (v[0] ^ (v[1] << 11)) & MASK64; v[3] = (v[3] + v[0]) & MASK64; v[1] = (v[1] + v[3]) & MASK64
    v[1] = (v[1] ^ (v[3] >> 2)) & MASK64; v[4] = (v[4] + v[1]) & MASK64; v[3] = (v[3] + v[4]) & MASK64
    v[3] = (v[3] ^ (v[4] << 8)) & MASK64; v[5] = (v[5] + v[3]) & MASK64; v[4] = (v[4] + v[5]) & MASK64
    v[4] = (v[4] ^ (v[5] >> 16)) & MASK64; v[6] = (v[6] + v[4]) & MASK64; v[5] = (v[5] + v[6]) & MASK64
    v[5] = (v[5] ^ (v[6] << 10)) & MASK64; v[7] = (v[7] + v[5]) & MASK64; v[6] = (v[6] + v[7]) & MASK64
    v[6] = (v[6] ^ (v[7] >> 4)) & MASK64; v[0] = (v[0] + v[6]) & MASK64; v[7] = (v[7] + v[0]) & MASK64
    v[7] = (v[7] ^ (v[0] << 8)) & MASK64; v[1] = (v[1] + v[7]) & MASK64; v[0] = (v[0] + v[1]) & MASK64
    v[0] = (v[0] ^ (v[1] >> 9)) & MASK64; v[2] = (v[2] + v[0]) & MASK64; v[1] = (v[1] + v[2]) & MASK64
    v[1] = (v[1] ^ (v[2] << 3)) & MASK64; v[3] = (v[3] + v[1]) & MASK64; v[2] = (v[2] + v[3]) & MASK64
    v[2] = (v[2] ^ (v[3] >> 10)) & MASK64; v[4] = (v[4] + v[2]) & MASK64; v[3] = (v[3] + v[4]) & MASK64
    v[3] = (v[3] ^ (v[4] << 15)) & MASK64; v[5] = (v[5] + v[3]) & MASK64; v[4] = (v[4] + v[5]) & MASK64


class ISAAC64:
    """ISAAC-64 随机数生成器（与 Go 版本一致）"""

    def __init__(self, key: int):
        self.mm = [0] * 256
        self.aa = 0
        self.bb = 0
        self.cc = 0
        self.rand_rsl = [0] * 256
        self.rand_cnt = 256
        self._init(key)

    def _init(self, key: int):
        # 初始化种子数组
        seed = [0] * 256
        seed[0] = key & MASK64

        # 第一轮：用 seed 初始化 mm
        v = [GOLDEN_RATIO] * 8
        for i in range(0, 256, 8):
            for j in range(8):
                v[j] = (v[j] + seed[i + j]) & MASK64
            _mix(v)
            for j in range(8):
                self.mm[i + j] = v[j]

        # 第二轮：用 mm 自身混合
        for i in range(0, 256, 8):
            for j in range(8):
                v[j] = (v[j] + self.mm[i + j]) & MASK64
            _mix(v)
            for j in range(8):
                self.mm[i + j] = v[j]

        # 生成第一批随机数
        self._isaac64()
        self.rand_cnt = 256

    def _isaac64(self):
        self.cc = (self.cc + 1) & MASK64
        self.bb = (self.bb + self.cc) & MASK64

        for i in range(256):
            x = self.mm[i]
            match i & 3:
                case 0:
                    self.aa = (self.aa ^ (self.aa << 13)) & MASK64
                case 1:
                    self.aa = (self.aa ^ (self.aa >> 6)) & MASK64
                case 2:
                    self.aa = (self.aa ^ (self.aa << 2)) & MASK64
                case 3:
                    self.aa = (self.aa ^ (self.aa >> 16)) & MASK64

            self.aa = (self.mm[(i + 128) & 0xFF] + self.aa) & MASK64
            y = (self.mm[(self.rand_rsl[i] >> 3) & 0xFF] + self.aa + self.bb) & MASK64
            self.mm[i] = y
            self.bb = (self.mm[(y >> 11) & 0xFF] + x) & MASK64
            self.rand_rsl[i] = self.bb

    def random(self) -> int:
        """返回一个 64 位随机数"""
        if self.rand_cnt == 0:
            self._isaac64()
            self.rand_cnt = 256
        self.rand_cnt -= 1
        return self.rand_rsl[self.rand_cnt]


# 默认加密长度：前 128KB
DEFAULT_ENC_LEN = 131072


def decrypt_isaac(data: bytearray, key: int, enc_len: int = DEFAULT_ENC_LEN) -> bytearray:
    """
    使用 ISAAC-64 流密码解密视频数据

    Args:
        data: 加密的视频数据（可变字节数组）
        key: 64 位解密密钥
        enc_len: 加密区域长度（默认 128KB）

    Returns:
        解密后的视频数据
    """
    if not data or not key:
        return data

    ctx = ISAAC64(key)
    actual_len = min(enc_len, len(data))

    for i in range(0, actual_len, 8):
        rand_number = ctx.random()
        # 大端序转字节
        rand_bytes = struct.pack('>Q', rand_number)
        remaining = min(8, actual_len - i)
        for j in range(remaining):
            data[i + j] ^= rand_bytes[j]

    return data
