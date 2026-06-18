"""跨进程一致的 SHA-256 哈希工具。

全项目唯一允许 import hashlib 的地方；业务代码只调 content_hash()。
（对应 CLAUDE.md 编码规则 4：缓存/去重 key 用 SHA-256，禁 Python hash()）
"""
import hashlib


def content_hash(text: str) -> str:
    """对文本做 SHA-256，返回十六进制摘要。跨进程一致，可作缓存/去重 key。

    Args:
        text: 待哈希的文本。
    Returns:
        64 字符十六进制 SHA-256 摘要。
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()