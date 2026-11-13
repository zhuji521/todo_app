# 应用入口。uvicorn 启动的就是这个文件里的 app 对象：
#     uvicorn app.main:app --host 0.0.0.0 --port 8000
# 它做四件事：记日志、按配置建表、挂上待办接口、把 frontend 的打包结果当成网站页面提供出去。
"""FastAPI 应用入口。

启动方式（在 backend 目录下）：
    uvicorn app.main:app --host 0.0.0.0 --port 8000

前端打包产物（index.html + static/）放在 backend/dist 下，
本应用会把它作为静态站点一起对外提供，所以生产环境只需暴露 8000 端口。
"""

# 允许 dict[str, str] 这种类型写法。
from __future__ import annotations

# logging 是 Python 标准日志。这里同时打到控制台和滚动文件。
import logging
# asynccontextmanager 把一个带 yield 的异步函数变成 FastAPI 的生命周期钩子。
from contextlib import asynccontextmanager
# 日志文件超过大小后自动改名备份，避免 app.log 无限变大。
from logging.handlers import RotatingFileHandler

# FastAPI 应用对象的类。
from fastapi import FastAPI
# 浏览器跨域中间件。开发时前端在 5173，需要它；同源部署时不必启用。
from fastapi.middleware.cors import CORSMiddleware
# FileResponse 返回磁盘上的文件。JSONResponse 返回 JSON，并可以指定状态码。
from fastapi.responses import FileResponse, JSONResponse
# StaticFiles 把一个目录整个挂到某个 URL 前缀下。
from fastapi.staticfiles import StaticFiles

# 导入 models 不是为了在本文件里用它，而是为了让 Todo、TodoLog 注册到 Base.metadata。
# 不导入的话，后面的 create_all 不知道要建哪两张表。noqa 是告诉检查器这个导入允许“未使用”。
from . import models  # noqa: F401  确保模型被注册到 Base.metadata
# BACKEND_DIR 是 backend 目录，DIST_DIR 是 backend/dist，settings 是全部配置。
from .config import BACKEND_DIR, DIST_DIR, settings
# Base.metadata 知道表结构；engine 是数据库连接池。
from .database import Base, engine
# 待办的全部 REST 接口。
from .routers import todos_router

# 日志目录固定为 backend/logs，不跟启动时的工作目录走。
LOG_DIR = BACKEND_DIR / "logs"
# 每条日志的格式：时间、级别、记录器名字、消息。
_log_format = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

# 取一个名叫 todo 的记录器。业务代码之外的库日志不会混进这个名字。
logger = logging.getLogger("todo")
# INFO 及以上才输出。DEBUG 默认不打。
logger.setLevel(logging.INFO)
# 防止模块被重复导入时加上两套处理器，否则同一条日志会打印两次。
if not logger.handlers:
    # 控制台处理器。Docker 里没写上文件时，仍可以靠 docker compose logs 看到。
    _console = logging.StreamHandler()
    _console.setFormatter(_log_format)
    logger.addHandler(_console)
    try:
        # 文件日志落盘到 backend/logs/app.log，容器里该目录已做卷映射
        # parents=True：logs 的上级不在也会一并创建。exist_ok=True：目录已在就不要报错。
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        # 单个文件 5MB，超出后保留最近 3 个备份（app.log.1 到 app.log.3）。
        _file = RotatingFileHandler(
            LOG_DIR / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        _file.setFormatter(_log_format)
        logger.addHandler(_file)
    # 目录没有写权限时（例如容器用户和挂载目录的属主不一致）不要让整个服务起不来。
    except OSError:
        # 第一个 %s 会被后面的 LOG_DIR 替换进这句警告。
        logger.warning("无法写入日志文件目录 %s，仅使用控制台输出", LOG_DIR)


# lifespan 在应用启动和关闭时各跑一半：yield 之前是启动，yield 之后是关闭。
# 这里没有关闭逻辑，所以 yield 后面是空的。
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 配置允许时，按 models 里登记的表建表。表已经存在则什么都不改，不会清空数据。
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
        logger.info("数据表检查/创建完成")
    # 没有前端打包目录只是警告。接口仍然可用，只是打开首页看不到页面。
    if not DIST_DIR.exists():
        logger.warning("未找到前端产物目录：%s（前端打包后放到该目录即可）", DIST_DIR)
    # yield 把控制权交给 FastAPI。服务运行期间停在这里，直到进程退出。
    yield


# 创建整个 Web 应用。/docs 页面的标题、版本和说明来自这几个参数。
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="待办清单服务：增删改查 + 历史记录",
    # 把上面的 lifespan 注册为启动钩子，服务起来时才会建表。
    lifespan=lifespan,
)

# 只有配置了允许的来源才加跨域中间件。空列表表示同源部署，不需要 CORS。
if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        # 例如开发环境的 http://127.0.0.1:5173。不在名单里的网页不能用浏览器调这个接口。
        allow_origins=settings.cors_origin_list,
        # 允许带 Cookie。当前接口没有登录，这项没有实际影响。
        allow_credentials=True,
        # 允许所有 HTTP 方法，包括前端用到的 GET、POST、PATCH、DELETE。
        allow_methods=["*"],
        # 允许所有请求头，包括 Content-Type: application/json。
        allow_headers=["*"],
    )

# 把 /api/todos 下的增删改查路由挂到应用上。
app.include_router(todos_router)


# 健康检查。Docker 的 HEALTHCHECK 和 compose 之外的探活都打这个地址。
# 它不访问数据库，所以只能说明进程还在，不能说明 MySQL 一定正常。
@app.get("/api/health", tags=["system"], summary="健康检查")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------- 静态前端 ----------
# Vite 把 js/css 放到 backend/dist/static。这里把该目录挂到网址 /static。
_assets_dir = DIST_DIR / "static"
# 目录不存在就不挂。开发时如果还没 npm run build，缺少静态目录不应阻止接口启动。
if _assets_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_assets_dir)), name="static")


# 网站根路径。include_in_schema=False：不要出现在 /docs 里，它是页面不是接口。
@app.get("/", include_in_schema=False)
def index():
    # 打包后的入口页面。
    index_file = DIST_DIR / "index.html"
    # 文件在就原样返回，浏览器会再去加载 ./static 里的 js 和 css。
    if index_file.is_file():
        return FileResponse(index_file)
    # 文件不在也返回 200，方便只启动后端时能看到一句明确提示，而不是一片空白。
    return JSONResponse(
        status_code=200,
        content={"message": "后端已启动，但未找到前端产物 backend/dist/index.html"},
    )


# 兜底路由。写在最后，前面的 /api/todos、/static、/ 都匹配不到时才进这里。
# {full_path:path} 会吃掉斜杠后面的整段路径，包括多层目录。
@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    """单页应用兜底路由：非 /api 路径一律回 index.html，避免刷新 404。"""
    # 未知的 /api/... 必须返回 JSON 404。如果也回 index.html，前端会把网页当成接口结果。
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "接口不存在"})

    # 把请求路径拼到 dist 目录下，并解析成绝对路径。
    candidate = (DIST_DIR / full_path).resolve()
    try:
        # relative_to 用来确认结果仍在 dist 里面。
        # 例如请求 /../.env 时，解析后的路径会跑出 dist，这里会抛 ValueError。
        candidate.relative_to(DIST_DIR.resolve())
    except ValueError:
        return JSONResponse(status_code=404, content={"detail": "文件不存在"})

    # 路径合法，而且磁盘上真有这个文件，就返回文件本身。
    if candidate.is_file():
        return FileResponse(candidate)

    # 不是真实文件时，当成前端路由，返回首页。刷新浏览器不会 404。
    index_file = DIST_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    # dist 里连首页都没有，只能告诉调用方文件不存在。
    return JSONResponse(status_code=404, content={"detail": "文件不存在"})
