# 配置层：把数据库地址、密码、是否自动建表等集中成一个 Settings 对象。
# 本地 uvicorn 和 Docker 用的是同一份代码，差别只在环境变量。
"""应用配置。

所有配置都可以通过环境变量覆盖，方便本地运行与 Docker 部署使用同一份代码。
配置文件路径统一相对 backend 目录解析，不依赖启动时的工作目录。
"""

# 允许写 list[str]、str | None 这种新式类型标注，不需要从 typing 再导入。
from __future__ import annotations

# Path 用来拼文件系统路径，比字符串拼接更能处理 Windows 的反斜杠。
from pathlib import Path

# BaseSettings：字段名会自动对应同名环境变量（大小写不敏感）。
# SettingsConfigDict：告诉它额外去读哪个 .env 文件。
from pydantic_settings import BaseSettings, SettingsConfigDict

# 本文件路径是 backend/app/config.py。
# parent 是 app 目录，再 parent 一次就是 backend 目录。
# resolve() 把相对路径变成绝对路径，这样无论从哪个目录启动都指向同一处。
# backend/ 目录（本文件位于 backend/app/config.py）
BACKEND_DIR = Path(__file__).resolve().parent.parent


# Settings 的每个字段都是一项配置。
# 字段默认值是“没设环境变量时用的值”；设了环境变量就用环境变量。
# 例如字段 db_host 对应环境变量 DB_HOST。
class Settings(BaseSettings):
    # model_config 是 pydantic-settings 的配置本身，不是业务配置。
    model_config = SettingsConfigDict(
        # 启动时再读 backend/.env。环境变量的优先级高于 .env 文件。
        env_file=str(BACKEND_DIR / ".env"),
        # .env 按 UTF-8 读，避免中文路径或注释乱码。
        env_file_encoding="utf-8",
        # .env 里多出来的、本类没有的字段直接忽略，不要因此启动失败。
        extra="ignore",
    )

    # 显示在 /docs 页面标题上的服务名。
    app_name: str = "Todo List API"
    # 运行环境标记。docker-compose 会把它设成 production。当前业务代码没有按它分支。
    app_env: str = "production"

    # ---- MySQL 连接参数 ----
    # 数据库主机。本机开发是 127.0.0.1；Docker 里 compose 会把它改成服务名 mysql。
    db_host: str = "127.0.0.1"
    # MySQL 端口。容器内部仍是 3306；compose 映射到宿主机时用的是 3307，那是给外部工具的。
    db_port: int = 3306
    # 业务账号。init.sql 创建的就是这个用户，应用不用 root 连接。
    db_user: str = "todo"
    # 默认密码，和 .env.example、init.sql 里的示例一致。正式环境要用环境变量换掉。
    db_password: str = "todo_pass_123"
    # 库名，对应 init.sql 里的 CREATE DATABASE todo_db。
    db_name: str = "todo_db"

    # 直接指定完整连接串时优先使用（例如本地用 sqlite 做冒烟测试）
    # 非空时 database_url 不再用上面的 host/port/user 去拼接。
    # smoke_test.py 会设置 DB_URL=sqlite:///...，从而不连接 MySQL。
    db_url: str = ""

    # 是否在启动时自动建表（生产环境建议用 sql/init.sql 手动建好）
    # True 时 main.py 启动会调用 create_all。已有的表不会被修改或清空。
    auto_create_tables: bool = True

    # 允许的跨域来源，逗号分隔；前后端同源部署时留空即可
    # 开发时前端在 5173、后端在 8000，需要在 backend/.env 里填上前端地址。
    cors_origins: str = ""

    # @property 让 database_url 可以像字段一样读取：settings.database_url。
    # 它不来自环境变量，而是根据上面的字段现算的。
    @property
    def database_url(self) -> str:
        # 显式给了完整连接串就直接用，例如 sqlite 冒烟测试。
        if self.db_url:
            return self.db_url
        # 否则拼成 SQLAlchemy 认识的 MySQL URL。
        # mysql+pymysql 表示用 PyMySQL 这个驱动去连。
        # charset=utf8mb4 让连接能正确读写中文和 emoji。
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    # 把逗号分隔的字符串拆成列表，供 CORS 中间件使用。
    @property
    def cors_origin_list(self) -> list[str]:
        # strip 去掉每段两端空格；空段丢掉，所以留空字符串时得到空列表。
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


# 进程内只建一份配置。其他模块统一 `from .config import settings`。
settings = Settings()

# 前端打包产物目录：backend/dist
# Vite 的 outDir 也指向这里。main.py 从这个目录提供 index.html 和 static/。
DIST_DIR = BACKEND_DIR / "dist"
