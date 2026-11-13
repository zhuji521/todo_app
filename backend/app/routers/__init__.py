# 从同目录的 todos.py 取出路由对象，并改名为 todos_router。
# main.py 里写的是 `from .routers import todos_router`，靠的就是这一行。
from .todos import router as todos_router

# 声明本包对外公开的名字。`from app.routers import *` 时只会导出 todos_router。
__all__ = ["todos_router"]
