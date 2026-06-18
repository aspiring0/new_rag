"""tests/unit/core/test_config.py — 配置管理单元测试（TDD）。"""
import pytest
from pydantic import ValidationError

from src.core.config import get_settings


def test_get_settings_reads_env(monkeypatch):
    """环境变量能被 Settings 正确读取。"""
    monkeypatch.setenv("LLM_API_KEY", "sk-test-123")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.llm_api_key.get_secret_value() == "sk-test-123"
    assert settings.redis_url == "redis://localhost:6379/0"


def test_invalid_int_field_raises_validation_error(monkeypatch):
    """非整数赋给 int 字段 → pydantic 拒绝（ValidationError）。"""
    monkeypatch.setenv("MILVUS_PORT", "not-a-number")
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()

def test_prod_mode_rejects_missing_required_key(monkeypatch):
    """prod 模式下关键 key 缺失 → 拒启动（ValidationError）。"""
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()
def test_dev_mode_allows_missing_required_key(monkeypatch):
    """dev 模式下关键 key 缺失 → 放行（不抛），方便本地开发。"""
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()

    settings = get_settings()  # dev 放行，不应抛异常
    assert settings.app_env == "dev"

def test_prod_mode_rejects_placeholder_values(monkeypatch):
    """prod 模式下关键 key 是占位值（changeme 等非空占位）→ 拒启动。"""
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("LLM_API_KEY", "changeme")  # 占位值，不是空串
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()

def test_get_settings_returns_cached_singleton(monkeypatch):
    """get_settings() 多次调用返回同一对象（lru_cache 单例）。"""
    monkeypatch.setenv("LLM_API_KEY", "sk-abc")
    get_settings.cache_clear()

    first = get_settings()
    second = get_settings()
    assert first is second  # is：同一个对象（身份），不是值相等


def test_cache_clear_reloads_new_env(monkeypatch):
    """cache_clear() 后，改了环境变量能被重新加载（测试隔离的基础）。"""
    monkeypatch.setenv("LLM_API_KEY", "sk-first")
    get_settings.cache_clear()
    first = get_settings()
    assert first.llm_api_key.get_secret_value() == "sk-first"

    monkeypatch.setenv("LLM_API_KEY", "sk-second")
    get_settings.cache_clear()
    second = get_settings()
    assert second.llm_api_key.get_secret_value() == "sk-second"
    assert first is not second  # 清缓存后是全新对象

def test_secret_fields_not_leaked_in_repr(monkeypatch):
    """敏感 key 不能出现在配置对象的 repr/str 里（防日志/堆栈泄露）。"""
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("LLM_API_KEY", "sk-super-secret-real-key-12345")
    get_settings.cache_clear()

    settings = get_settings()

    assert "sk-super-secret-real-key-12345" not in repr(settings)
    assert "sk-super-secret-real-key-12345" not in str(settings)