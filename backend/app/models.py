# ORM 模型：用 Python 类描述 MySQL 里的两张表。
# 类的字段要和 backend/sql/init.sql 里的列对应。
# 这里不写查询；查询在 crud.py。
# 对，models 就是表的设计图。 
# 它规定每张表有哪些字段、什么类型、能不能空、默认是什么，数据库就按这个建出来。
"""ORM 模型。"""

# 允许 datetime | None 这种写法。
from __future__ import annotations

# 时间字段在 Python 侧用 datetime 表示。
from datetime import datetime

# 这些是列类型，对应 MySQL 的类型：
# Boolean -> TINYINT(1)，DateTime -> DATETIME，Integer -> INT，String(n) -> VARCHAR(n)。
# func 用来在 SQL 里写 now()，作为数据库侧的默认时间。
from sqlalchemy import Boolean, DateTime, Integer, String, func
# Mapped[类型] 声明“这一列在 Python 里是什么类型”。
# mapped_column(...) 声明“这一列在数据库里怎么建”。
from sqlalchemy.orm import Mapped, mapped_column

# Base 是 database.py 里的公共父类。继承它，这张表才会被注册进 metadata。
from .database import Base


# 一条待办。表名 todos，和 init.sql 的 CREATE TABLE `todos` 是同一张表。
class Todo(Base):
    # 显式指定表名。不写的话 SQLAlchemy 会按类名自己起名。
    __tablename__ = "todos"

    # 主键，数据库自增。INT，对应 init.sql 的 INT UNSIGNED AUTO_INCREMENT。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 待办正文，最长 500，不允许空。接口层还会再去掉首尾空格。
    content: Mapped[str] = mapped_column(String(500), nullable=False)
    # 是否完成。Python 里是 bool；数据库默认 0，也就是未完成。
    # default 是 Python 插入时用的值，server_default 是数据库自己的默认值。
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")

    # 创建时间。Python 插入时用 datetime.now()；纯 SQL 插入时用数据库的 CURRENT_TIMESTAMP。
    # 应用容器时区是 Asia/Shanghai，所以 now() 是北京时间。
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, server_default=func.now()
    )
    # 更新时间。onupdate 让 SQLAlchemy 在这条记录被修改并提交时改成当前时间。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        server_default=func.now(),
    )
    # 完成时间。未完成时是 NULL，所以类型是 datetime | None。
    # 勾选完成时 crud.py 写入当前时间，取消完成时写回 None。
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 调试时打印这个对象用的字符串。pragma 告诉覆盖率工具不用统计这一行。
    def __repr__(self) -> str:  # pragma: no cover
        # !r 会给内容加上引号并转义，方便在日志里看清空格。
        return f"<Todo id={self.id} completed={self.completed} content={self.content!r}>"


# 操作流水。删除待办时只删 todos 里的行，这里的记录会留下来。
class TodoLog(Base):
    """待办操作流水，用于前端展示历史轨迹（可选功能）。"""

    # 对应 init.sql 的 todo_logs。
    __tablename__ = "todo_logs"

    # 流水自己的主键，不是待办 id。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 这条流水属于哪条待办。index=True 会建索引，按待办查历史时更快。
    # 这里没有建外键：待办被删之后，流水仍然要保留。
    todo_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # 动作种类，最长 20。实际取值是 create、update_content、complete、reopen、delete。
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    # 给人看的描述，例如“新建待办：买牛奶”。空描述用空字符串，不用 NULL。
    detail: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # 动作发生的时间，并建索引。历史列表按这个字段倒序。
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, server_default=func.now(), index=True
    )
