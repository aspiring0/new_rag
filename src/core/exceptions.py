"""统一异常体系：自定义异常层次 + 异常→HTTP 状态码唯一映射表。

设计依据：docs/design/infra_blueprint.md L4 节、ADR-0001 决策 5。
核心原则：每个异常类自带 http_status 类属性 —— 状态码与类定义在一起，单一真相源。
"""
from typing import ClassVar


class RagError(Exception):
    """所有自定义业务异常的基类。

    子类通过覆盖 http_status 类属性声明自己的 HTTP 状态码。
    基类默认 500：万一某个异常漏定义状态码，至少回退到合理的"内部错误"而非崩 AttributeError。

    Args:
        message: 人类可读的错误描述。
        details: 可选的额外上下文（如出错字段、tenant_id），供日志和统一响应体使用。
    """

    # ClassVar 标注 = "类属性"，不是实例字段。全项目靠它做异常→HTTP 映射。
    http_status: ClassVar[int] = 500

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

class StorageError(RagError):
    """存储/连接故障：Redis/Milvus/Neo4j 不可达。映射 503。"""
    http_status: ClassVar[int] = 503


class RetrievalError(RagError):
    """检索内部错误：混合检索/RRF 融合出 bug。映射 500。"""
    http_status: ClassVar[int] = 500


class ValidationError(RagError):
    """输入校验失败：query 过长、参数非法。映射 422。"""
    http_status: ClassVar[int] = 422


class AuthError(RagError):
    """认证类异常基类：未认证（没登录/token 失效）。映射 401。"""
    http_status: ClassVar[int] = 401


class PermissionDeniedError(AuthError):
    """已认证但无权限访问该资源（越权）。映射 403。"""
    http_status: ClassVar[int] = 403


class QuotaExceeded(AuthError):
    """超出调用配额/触发限流。映射 429。"""
    http_status: ClassVar[int] = 429


class NotFoundError(RagError):
    """资源不存在：文档/租户查不到。映射 404。"""
    http_status: ClassVar[int] = 404
