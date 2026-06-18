"""配置管理：全项目唯一配置源（pydantic-settings + fail-fast 启动校验）。"""

# 从 Python 标准库 functools 中导入 lru_cache 装饰器
# lru_cache 的全称是 Least Recently Used Cache（最近最少使用缓存）
# 它的作用就是：把函数的执行结果缓存起来，下次调用时直接返回缓存，不重新执行函数体
from functools import lru_cache

from pydantic import SecretStr, model_validator



# 从第三方库 pydantic_settings 中导入两个核心组件：
# BaseSettings: 专门用来读取和管理配置（如环境变量、.env文件）的基类
# SettingsConfigDict: Pydantic V2 版本用来配置 BaseSettings 行为的字典类
from pydantic_settings import BaseSettings, SettingsConfigDict
# prod 模式必须配置真实值的关键 key —— 缺一不可，否则拒启动
_REQUIRED_KEYS: tuple[str, ...] = (
    "llm_api_key", "embedding_api_key", "redis_url", "jwt_secret",
)

# 占位值黑名单：这些值视为「未真正配置」
_PLACEHOLDER_VALUES: frozenset[str] = frozenset(
    {"", "changeme", "your-key", "xxx", "sk-xxx"}
)
# 定义一个配置类，继承自 BaseSettings
# 继承后，这个类就自动拥有了读取环境变量和 .env 文件的能力
class Settings(BaseSettings):
    """全项目配置项集合。"""

    # 配置类的行为参数：
    # env_file=".env" 表示启动时会自动读取当前目录下的 .env 文件
    # extra="ignore" 表示如果 .env 文件里有这个类没定义的变量，直接忽略，不报错
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")  

    app_env: str = "dev"          # dev / prod，决定 fail-fast 是否生效

    # 定义具体的配置项，冒号后面是类型提示，等号后面是默认值
    # 如果环境变量或 .env 中有 LLM_API_KEY，会自动赋值给这里；如果没有，就用空字符串
    llm_api_key: SecretStr = SecretStr("")
    embedding_api_key: SecretStr = SecretStr("")
    redis_url: str = "redis://localhost:6379/0"   # 连接地址，不是 secret，保持 str
    jwt_secret: SecretStr = SecretStr("")

    milvus_port: int = 19530  # 新增：int 类型，pydantic 自动校验


    @model_validator(mode="after")
    def _validate_required_keys(self) -> "Settings":
        """
        fail-fast：prod 模式下关键 key 缺失或为占位值 → raise ValueError。
        pydantic 会把 ValueError 包装成 ValidationError 抛出。dev 模式放行。
        """
        if self.app_env != "prod":
            return self  # dev 放行，方便本地开发

        # TODO（你写，3-4 行）：
        #   遍历 _REQUIRED_KEYS，
        #   用 getattr(self, key) 取出每个 key 的值，
        #   若值在 _PLACEHOLDER_VALUES 里 → raise ValueError(f"prod 模式下 {key} 必须配置真实值")
        for key in _REQUIRED_KEYS:
            value = getattr(self, key)
            # SecretStr 要先取明文再判断；redis_url 是普通 str 直接判断
            raw = value.get_secret_value() if isinstance(value, SecretStr) else value
            if raw in _PLACEHOLDER_VALUES:
                raise ValueError(f"prod 模式下 {key} 必须配置真实值")
        return self


# 【核心装饰器应用点】
# @lru_cache 加在这个函数上面，意味着这个函数的返回值会被缓存
# 因为配置在整个项目中是不变的，所以只需要读取一次，后面全部用缓存
@lru_cache
def get_settings() -> Settings:
    """全项目唯一配置入口。测试用 cache_clear() 换环境重载。"""
    # 实例化配置类。Pydantic 会在这里进行 Fail-Fast（快速失败）校验
    # 如果缺少必填项或类型不对，程序会在这里直接报错停止
    return Settings()