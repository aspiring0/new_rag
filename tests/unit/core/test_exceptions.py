"""tests/unit/core/test_exceptions.py — 异常体系单元测试（TDD）。"""
import pytest

from src.core.exceptions import (
    AuthError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceeded,
    RagError,
    RetrievalError,
    StorageError,
    ValidationError,
)


@pytest.mark.parametrize(
    "exc_cls, expected_status",
    [
        (RagError, 500),
        (StorageError, 503),
        (RetrievalError, 500),
        (ValidationError, 422),
        (AuthError, 401),
        (PermissionDeniedError, 403),
        (QuotaExceeded, 429),
        (NotFoundError, 404),
    ],
)
def test_http_status_mapping(exc_cls: type, expected_status: int) -> None:
    """每个异常类的 http_status 必须等于映射表约定值（P0-04 灵魂测试）。"""
    assert exc_cls.http_status == expected_status


@pytest.mark.parametrize(
    "exc_cls",
    [
        StorageError,
        RetrievalError,
        ValidationError,
        AuthError,
        PermissionDeniedError,
        QuotaExceeded,
        NotFoundError,
    ],
)
def test_all_subclasses_are_rag_errors(exc_cls: type) -> None:
    """所有业务异常都是 RagError 的子类（统一异常根，便于 Phase2 兜底捕获）。"""
    assert issubclass(exc_cls, RagError)


@pytest.mark.parametrize(
    "exc_cls",
    [PermissionDeniedError, QuotaExceeded],
)
def test_auth_subclasses_inherit_auth_error(exc_cls: type) -> None:
    """PermissionDenied / QuotaExceeded 都继承 AuthError（蓝图层次关键）。"""
    assert issubclass(exc_cls, AuthError)


def test_rag_error_falls_back_to_500() -> None:
    """基类 RagError 默认 500（子类漏定义状态码时的兜底，而非崩 AttributeError）。"""
    assert RagError.http_status == 500


def test_message_and_details_stored() -> None:
    """构造异常时传入的 message 和 details 能取回（供日志和统一响应体）。"""
    err = StorageError("redis 连接超时", {"host": "10.0.0.1", "port": 6379})
    assert err.message == "redis 连接超时"
    assert err.details == {"host": "10.0.0.1", "port": 6379}


def test_details_defaults_to_empty_dict() -> None:
    """不传 details 时默认空 dict（防止下游 err.details["x"] 取到 None 而崩）。"""
    err = StorageError("redis 连接超时")
    assert err.details == {}


def test_subclass_caught_by_base() -> None:
    """raise 子类异常，能被 except 父类捕获（Python 继承多态，Phase2 handler 依赖它）。"""
    with pytest.raises(RagError):
        raise StorageError("redis down")
