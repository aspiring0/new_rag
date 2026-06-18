"""tests/unit/core/test_hash.py — content_hash 单元测试（TDD）。"""
import subprocess
import sys

from src.core.hash import content_hash


def test_content_hash_returns_hex_of_fixed_length():
    """返回 64 字符十六进制（SHA-256 摘要长度）。"""
    result = content_hash("hello")
    assert len(result) == 64
    int(result, 16)  # 能转成整数 = 都是合法 hex 字符


def test_content_hash_matches_known_sha256_value():
    """与已知 SHA-256 值一致（证明用的是 SHA-256 算法）。"""
    # 这是 SHA-256("hello") 的标准值，可用 echo -n hello | sha256sum 验证
    assert content_hash("hello") == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_content_hash_is_deterministic():
    """同样输入 → 同样输出。"""
    assert content_hash("abc") == content_hash("abc")


def test_content_hash_different_inputs_differ():
    """不同输入 → 不同输出。"""
    assert content_hash("abc") != content_hash("abd")


def test_content_hash_consistent_across_processes():
    """跨进程一致（subprocess）—— 用 SHA-256 替代 Python hash() 的核心原因。"""
    in_proc = content_hash("cross-process-test")
    out = subprocess.check_output(
        [sys.executable, "-c",
         "from src.core.hash import content_hash; print(content_hash('cross-process-test'))"],
    )
    assert out.decode().strip() == in_proc
