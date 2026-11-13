# 这个文件让 backend/app 成为一个 Python 包。
# 其他地方写 `from app.xxx import ...` 时，Python 会先执行本文件。
"""Todo List 后端应用包。"""

# 应用版本号。main.py 里创建 FastAPI 时写的版本是另一处字面量，这里单独标一份。
__version__ = "1.0.0"
