"""抖音 Web API a_bogus 反爬签名 —— 纯 Python 移植（无第三方依赖）

算法移植自开源项目 f2 (https://github.com/Johnserf-Seed/f2, Apache-2.0)
的 f2/utils/abogus.py，用纯标准库重写了其依赖的 SM3 哈希（原版依赖 gmssl）。

⚠ 维护须知：
  a_bogus 是抖音前端 JSVM 生成的反爬签名，会随抖音前端版本更新而变动
  常量/算法。失效表现：调用官方 API 返回 200 但 body 为 0 字节，或
  aweme_list 为空。届时需对照 f2 上游同步更新本文件的常量数组与流程。

对外只暴露 get_a_bogus(params, user_agent) -> str。
"""

import time
import random
from typing import Callable, Dict, List, Union

# ─── 纯 Python SM3（替代 gmssl） ─────────────────────────
_SM3_IV = [
    0x7380166F, 0x4914B2B9, 0x172442D7, 0xDA8A0600,
    0xA96F30BC, 0x163138AA, 0xE38DEE4D, 0xB0FB0E4E,
]


def _rotl(x: int, n: int) -> int:
    n %= 32
    x &= 0xFFFFFFFF
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _sm3_hash(msg: List[int]) -> str:
    """SM3 摘要。输入字节整数列表，返回 64 位十六进制字符串。"""
    length = len(msg)
    m = list(msg)
    m.append(0x80)
    while len(m) % 64 != 56:
        m.append(0x00)
    bit_len = length * 8
    for i in range(8):
        m.append((bit_len >> (56 - i * 8)) & 0xFF)

    v = _SM3_IV[:]
    for off in range(0, len(m), 64):
        block = m[off:off + 64]
        w = []
        for j in range(16):
            w.append((block[j * 4] << 24) | (block[j * 4 + 1] << 16)
                     | (block[j * 4 + 2] << 8) | block[j * 4 + 3])
        for j in range(16, 68):
            w.append(
                (_rotl(w[j - 3], 15) ^ w[j - 9] ^ w[j - 16])
            )
            x = w[j]
            x = x ^ _rotl(x, 15) ^ _rotl(x, 23)  # P1
            w[j] = (x ^ _rotl(w[j - 13], 7) ^ w[j - 6]) & 0xFFFFFFFF
        w1 = [(w[j] ^ w[j + 4]) & 0xFFFFFFFF for j in range(64)]

        a, b, c, d, e, f, g, h = v
        for j in range(64):
            tj = 0x79CC4519 if j < 16 else 0x7A879D8A
            ss1 = _rotl((_rotl(a, 12) + e + _rotl(tj, j)) & 0xFFFFFFFF, 7)
            ss2 = ss1 ^ _rotl(a, 12)
            if j < 16:
                ff = a ^ b ^ c
                gg = e ^ f ^ g
            else:
                ff = (a & b) | (a & c) | (b & c)
                gg = (e & f) | (~e & g)
            tt1 = (ff + d + ss2 + w1[j]) & 0xFFFFFFFF
            tt2 = (gg + h + ss1 + w[j]) & 0xFFFFFFFF
            d = c
            c = _rotl(b, 9)
            b = a
            a = tt1
            h = g
            g = _rotl(f, 19)
            f = e
            e = tt2 ^ _rotl(tt2, 9) ^ _rotl(tt2, 17)  # P0
        v = [
            (v[0] ^ a) & 0xFFFFFFFF, (v[1] ^ b) & 0xFFFFFFFF,
            (v[2] ^ c) & 0xFFFFFFFF, (v[3] ^ d) & 0xFFFFFFFF,
            (v[4] ^ e) & 0xFFFFFFFF, (v[5] ^ f) & 0xFFFFFFFF,
            (v[6] ^ g) & 0xFFFFFFFF, (v[7] ^ h) & 0xFFFFFFFF,
        ]
    return "".join("%08x" % x for x in v)


# ─── 以下为 f2 abogus.py 忠实移植 ────────────────────────
class StringProcessor:
    @staticmethod
    def to_ord_str(s: str) -> str:
        return "".join([chr(i) for i in s])

    @staticmethod
    def to_char_str(s) -> str:
        return "".join([chr(i) for i in s])

    @staticmethod
    def to_char_array(s: str) -> List[int]:
        return [ord(char) for char in s]

    @staticmethod
    def js_shift_right(val: int, n: int) -> int:
        return (val % 0x100000000) >> n

    @staticmethod
    def generate_random_bytes(length: int = 3) -> str:
        def generate_byte_sequence() -> List[str]:
            _rd = int(random.random() * 10000)
            return [
                chr(((_rd & 255) & 170) | 1),
                chr(((_rd & 255) & 85) | 2),
                chr((StringProcessor.js_shift_right(_rd, 8) & 170) | 5),
                chr((StringProcessor.js_shift_right(_rd, 8) & 85) | 40),
            ]

        result = []
        for _ in range(length):
            result.extend(generate_byte_sequence())
        return "".join(result)


class CryptoUtility:
    def __init__(self, salt: str, custom_base64_alphabet: List[str]):
        self.salt = salt
        self.base64_alphabet = custom_base64_alphabet
        # fmt: off
        self.big_array = [
            121, 243,  55, 234, 103,  36,  47, 228,  30, 231, 106,   6, 115,  95,  78, 101, 250, 207, 198,  50,
            139, 227, 220, 105,  97, 143,  34,  28, 194, 215,  18, 100, 159, 160,  43,   8, 169, 217, 180, 120,
            247,  45,  90,  11,  27, 197,  46,   3,  84,  72,   5,  68,  62,  56, 221,  75, 144,  79,  73, 161,
            178,  81,  64, 187, 134, 117, 186, 118,  16, 241, 130,  71,  89, 147, 122, 129,  65,  40,  88, 150,
            110, 219, 199, 255, 181, 254,  48,   4, 195, 248, 208,  32, 116, 167,  69, 201,  17, 124, 125, 104,
             96,  83,  80, 127, 236, 108, 154, 126, 204,  15,  20, 135, 112, 158,  13,   1, 188, 164, 210, 237,
            222,  98, 212,  77, 253,  42, 170, 202,  26,  22,  29, 182, 251,  10, 173, 152,  58, 138,  54, 141,
            185,  33, 157,  31, 252, 132, 233, 235, 102, 196, 191, 223, 240, 148,  39, 123,  92,  82, 128, 109,
             57,  24,  38, 113, 209, 245,   2, 119, 153, 229, 189, 214, 230, 174, 232,  63,  52, 205,  86, 140,
             66, 175, 111, 171, 246, 133, 238, 193,  99,  60,  74,  91, 225,  51,  76,  37, 145, 211, 166, 151,
            213, 206,   0, 200, 244, 176, 218,  44, 184, 172,  49, 216,  93, 168,  53,  21, 183,  41,  67,  85,
            224, 155, 226, 242,  87, 177, 146,  70, 190,  12, 162,  19, 137, 114,  25, 165, 163, 192,  23,  59,
              9,  94, 179, 107,  35,   7, 142, 131, 239, 203, 149, 136,  61, 249,  14, 156,
        ]
        # fmt: on

    @staticmethod
    def sm3_to_array(input_data: Union[str, List[int]]) -> List[int]:
        if isinstance(input_data, str):
            input_bytes = list(input_data.encode("utf-8"))
        else:
            input_bytes = list(input_data)
        hex_result = _sm3_hash(input_bytes)
        return [int(hex_result[i:i + 2], 16) for i in range(0, len(hex_result), 2)]

    def add_salt(self, param: str) -> str:
        return param + self.salt

    def process_param(self, param, add_salt: bool):
        if isinstance(param, str) and add_salt:
            param = self.add_salt(param)
        return param

    def params_to_array(self, param, add_salt: bool = True) -> List[int]:
        processed_param = self.process_param(param, add_salt)
        return self.sm3_to_array(processed_param)

    def transform_bytes(self, bytes_list: List[int]) -> str:
        bytes_str = StringProcessor.to_char_str(bytes_list)
        result_str = []
        index_b = self.big_array[1]
        initial_value = 0
        value_e = 0

        for index, char in enumerate(bytes_str):
            if index == 0:
                initial_value = self.big_array[index_b]
                sum_initial = index_b + initial_value
                self.big_array[1] = initial_value
                self.big_array[index_b] = index_b
            else:
                sum_initial = initial_value + value_e

            char_value = ord(char)
            sum_initial %= len(self.big_array)
            value_f = self.big_array[sum_initial]
            encrypted_char = char_value ^ value_f
            result_str.append(chr(encrypted_char))

            value_e = self.big_array[(index + 2) % len(self.big_array)]
            sum_initial = (index_b + value_e) % len(self.big_array)
            initial_value = self.big_array[sum_initial]
            self.big_array[sum_initial] = self.big_array[(index + 2) % len(self.big_array)]
            self.big_array[(index + 2) % len(self.big_array)] = initial_value
            index_b = sum_initial

        return "".join(result_str)

    def base64_encode(self, input_string: str, selected_alphabet: int = 0) -> str:
        binary_string = "".join(["{:08b}".format(ord(char)) for char in input_string])
        padding_length = (6 - len(binary_string) % 6) % 6
        binary_string += "0" * padding_length
        base64_indices = [
            int(binary_string[i:i + 6], 2) for i in range(0, len(binary_string), 6)
        ]
        output_string = "".join(
            [self.base64_alphabet[selected_alphabet][index] for index in base64_indices]
        )
        output_string += "=" * (padding_length // 2)
        return output_string

    def abogus_encode(self, abogus_bytes_str: str, selected_alphabet: int) -> str:
        abogus = []
        for i in range(0, len(abogus_bytes_str), 3):
            if i + 2 < len(abogus_bytes_str):
                n = ((ord(abogus_bytes_str[i]) << 16)
                     | (ord(abogus_bytes_str[i + 1]) << 8)
                     | ord(abogus_bytes_str[i + 2]))
            elif i + 1 < len(abogus_bytes_str):
                n = (ord(abogus_bytes_str[i]) << 16) | (ord(abogus_bytes_str[i + 1]) << 8)
            else:
                n = ord(abogus_bytes_str[i]) << 16

            for j, k in zip(range(18, -1, -6), (0xFC0000, 0x03F000, 0x0FC0, 0x3F)):
                if j == 6 and i + 1 >= len(abogus_bytes_str):
                    break
                if j == 0 and i + 2 >= len(abogus_bytes_str):
                    break
                abogus.append(self.base64_alphabet[selected_alphabet][(n & k) >> j])

        abogus.append("=" * ((4 - len(abogus) % 4) % 4))
        return "".join(abogus)

    @staticmethod
    def rc4_encrypt(key: bytes, plaintext: str) -> bytes:
        s = list(range(256))
        j = 0
        for i in range(256):
            j = (j + s[i] + key[i % len(key)]) % 256
            s[i], s[j] = s[j], s[i]

        i = j = 0
        ciphertext = []
        for char in plaintext:
            i = (i + 1) % 256
            j = (j + s[i]) % 256
            s[i], s[j] = s[j], s[i]
            k = s[(s[i] + s[j]) % 256]
            ciphertext.append(ord(char) ^ k)
        return bytes(ciphertext)


class BrowserFingerprintGenerator:
    @classmethod
    def generate_fingerprint(cls, browser_type: str = "Edge") -> str:
        return cls._generate_fingerprint(platform="Win32")

    @staticmethod
    def _generate_fingerprint(platform: str) -> str:
        inner_width = random.randint(1024, 1920)
        inner_height = random.randint(768, 1080)
        outer_width = inner_width + random.randint(24, 32)
        outer_height = inner_height + random.randint(75, 90)
        screen_x = 0
        screen_y = random.choice([0, 30])
        size_width = random.randint(1024, 1920)
        size_height = random.randint(768, 1080)
        avail_width = random.randint(1280, 1920)
        avail_height = random.randint(800, 1080)
        return (
            f"{inner_width}|{inner_height}|{outer_width}|{outer_height}|"
            f"{screen_x}|{screen_y}|0|0|{size_width}|{size_height}|"
            f"{avail_width}|{avail_height}|{inner_width}|{inner_height}|24|24|{platform}"
        )


class ABogus:
    def __init__(self, fp: str = "", user_agent: str = "", options: List[int] = None):
        self.aid = 6383
        self.pageId = 0
        self.salt = "cus"
        self.boe = False
        self.ddrt = 8.5
        self.ic = 8.5
        self.paths = [
            "^/webcast/", "^/aweme/v1/", "^/aweme/v2/", "/v1/message/send",
            "^/live/", "^/captcha/", "^/ecom/",
        ]
        self.array1 = []
        self.array2 = []
        self.array3 = []
        self.options = options if options is not None else [0, 1, 14]
        self.ua_key = b"\x00\x01\x0E"
        self.character = "Dkdpgh2ZmsQB80/MfvV36XI1R45-WUAlEixNLwoqYTOPuzKFjJnry79HbGcaStCe"
        self.character2 = "ckdp1h4ZKsUB80/Mfvw36XIgR25+WQAlEi7NLboqYTOPuzmFjJnryx9HVGDaStCe"
        self.character_list = [self.character, self.character2]
        self.crypto_utility = CryptoUtility(self.salt, self.character_list)
        self.user_agent = (
            user_agent if user_agent else
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
        )
        self.browser_fp = fp if fp else BrowserFingerprintGenerator.generate_fingerprint("Edge")
        # fmt: off
        self.sort_index = [
            18, 20, 52, 26, 30, 34, 58, 38, 40, 53, 42, 21, 27, 54, 55, 31, 35, 57, 39, 41, 43, 22, 28,
            32, 60, 36, 23, 29, 33, 37, 44, 45, 59, 46, 47, 48, 49, 50, 24, 25, 65, 66, 70, 71,
        ]
        self.sort_index_2 = [
            18, 20, 26, 30, 34, 38, 40, 42, 21, 27, 31, 35, 39, 41, 43, 22, 28, 32, 36, 23, 29, 33, 37,
            44, 45, 46, 47, 48, 49, 50, 24, 25, 52, 53, 54, 55, 57, 58, 59, 60, 65, 66, 70, 71,
        ]
        # fmt: on

    def generate_abogus(self, params: str, body: str = "") -> tuple:
        ab_dir = {
            8: 3,
            15: {
                "aid": self.aid, "pageId": self.pageId, "boe": self.boe,
                "ddrt": self.ddrt, "paths": self.paths,
                "track": {"mode": 0, "delay": 300, "paths": []},
                "dump": True, "rpU": "",
            },
            18: 44, 19: [1, 0, 1, 0, 1],
            66: 0, 69: 0, 70: 0, 71: 0,
        }

        start_encryption = int(time.time() * 1000)
        array1 = self.crypto_utility.params_to_array(
            self.crypto_utility.params_to_array(params))
        array2 = self.crypto_utility.params_to_array(
            self.crypto_utility.params_to_array(body))
        array3 = self.crypto_utility.params_to_array(
            self.crypto_utility.base64_encode(
                StringProcessor.to_ord_str(
                    self.crypto_utility.rc4_encrypt(self.ua_key, self.user_agent)), 1),
            add_salt=False)
        end_encryption = int(time.time() * 1000)

        ab_dir[20] = (start_encryption >> 24) & 255
        ab_dir[21] = (start_encryption >> 16) & 255
        ab_dir[22] = (start_encryption >> 8) & 255
        ab_dir[23] = start_encryption & 255
        ab_dir[24] = int(start_encryption / 256 / 256 / 256 / 256) >> 0
        ab_dir[25] = int(start_encryption / 256 / 256 / 256 / 256 / 256) >> 0
        ab_dir[26] = (self.options[0] >> 24) & 255
        ab_dir[27] = (self.options[0] >> 16) & 255
        ab_dir[28] = (self.options[0] >> 8) & 255
        ab_dir[29] = self.options[0] & 255
        ab_dir[30] = int(self.options[1] / 256) & 255
        ab_dir[31] = (self.options[1] % 256) & 255
        ab_dir[32] = (self.options[1] >> 24) & 255
        ab_dir[33] = (self.options[1] >> 16) & 255
        ab_dir[34] = (self.options[2] >> 24) & 255
        ab_dir[35] = (self.options[2] >> 16) & 255
        ab_dir[36] = (self.options[2] >> 8) & 255
        ab_dir[37] = self.options[2] & 255
        ab_dir[38] = array1[21]
        ab_dir[39] = array1[22]
        ab_dir[40] = array2[21]
        ab_dir[41] = array2[22]
        ab_dir[42] = array3[23]
        ab_dir[43] = array3[24]
        ab_dir[44] = (end_encryption >> 24) & 255
        ab_dir[45] = (end_encryption >> 16) & 255
        ab_dir[46] = (end_encryption >> 8) & 255
        ab_dir[47] = end_encryption & 255
        ab_dir[48] = ab_dir[8]
        ab_dir[49] = int(end_encryption / 256 / 256 / 256 / 256) >> 0
        ab_dir[50] = int(end_encryption / 256 / 256 / 256 / 256 / 256) >> 0
        ab_dir[51] = (self.pageId >> 24) & 255
        ab_dir[52] = (self.pageId >> 16) & 255
        ab_dir[53] = (self.pageId >> 8) & 255
        ab_dir[54] = self.pageId & 255
        ab_dir[55] = self.pageId
        ab_dir[56] = self.aid
        ab_dir[57] = self.aid & 255
        ab_dir[58] = (self.aid >> 8) & 255
        ab_dir[59] = (self.aid >> 16) & 255
        ab_dir[60] = (self.aid >> 24) & 255
        ab_dir[64] = len(self.browser_fp)
        ab_dir[65] = len(self.browser_fp)

        sorted_values = [ab_dir.get(i, 0) for i in self.sort_index]
        edge_fp_array = StringProcessor.to_char_array(self.browser_fp)

        ab_xor = (len(self.browser_fp) & 255) >> 8 & 255
        for index in range(len(self.sort_index_2) - 1):
            if index == 0:
                ab_xor = ab_dir.get(self.sort_index_2[index], 0)
            ab_xor ^= ab_dir.get(self.sort_index_2[index + 1], 0)

        sorted_values.extend(edge_fp_array)
        sorted_values.append(ab_xor)

        abogus_bytes_str = (
            StringProcessor.generate_random_bytes()
            + self.crypto_utility.transform_bytes(sorted_values))
        abogus = self.crypto_utility.abogus_encode(abogus_bytes_str, 0)
        params = "%s&a_bogus=%s" % (params, abogus)
        return (params, abogus, self.user_agent, body)


def get_a_bogus(params: str, user_agent: str) -> str:
    """为抖音 Web API GET 请求生成 a_bogus 签名值。

    Args:
        params: 不含前导 ? 的查询串（须与实际请求完全一致）。
        user_agent: 须与实际请求 UA 一致（用 _utils.DESKTOP_UA）。

    Returns:
        a_bogus 签名字符串。
    """
    ab = ABogus(user_agent=user_agent)
    return ab.generate_abogus(params, "")[1]
