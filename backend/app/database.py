# 数据库连接层：创建引擎、会话工厂，以及每个请求借用一次会话的函数。
# 业务代码不自己 new 连接，而是通过 get_db() 拿到 Session。
"""数据库引擎与会话管理。"""

# 允许下面的返回类型写成 Generator[Session, None, None]。
from __future__ import annotations

# Generator 用来标注 get_db 是一个生成器（里面有 yield）。
from collections.abc import Generator

# create_engine：按连接串建立一个可复用的数据库连接池。
from sqlalchemy import create_engine
# DeclarativeBase：所有 ORM 模型继承它，SQLAlchemy 才能知道有哪些表。
# Session：一次数据库会话，查询和提交都通过它。
# sessionmaker：用来按同一套参数批量制造 Session。
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# 连接串来自 config.py，本文件不关心主机和密码怎么来的。
from .config import settings


# 所有模型（Todo、TodoLog）都继承这个 Base。
# Base.metadata 里会登记它们对应的表，启动时 create_all 用的就是这份登记。
class Base(DeclarativeBase):
    # 这个类本身没有字段，只当所有模型的公共父类。
    pass


# 引擎是连接池，整个进程共用一个，不要每个请求新建。
engine = create_engine(
    # settings.database_url 可能是 mysql+pymysql://...，也可能是 sqlite:///...。
    settings.database_url,
    # 从池里取出连接前先发一次探测。MySQL 把空闲连接掐掉后，不会把死连接交给请求。
    pool_pre_ping=True,
    # 连接最多复用 1800 秒（30 分钟），之后回收重建，避免超过 MySQL 的 wait_timeout。
    pool_recycle=1800,
    # 不把每条 SQL 打印到日志。调试时可以临时改成 True。
    echo=False,
    # 使用 SQLAlchemy 2.0 的引擎行为。
    future=True,
)

# Session 工厂。bind 指定用上面的引擎。
# autoflush=False：查询前不自动把挂起的改动刷进数据库，由业务代码显式 flush/commit。
# autocommit=False：必须调用 commit() 才真正提交，否则请求结束时的改动不会落库。
# expire_on_commit=False：提交后对象属性仍可读取，不必再查一次库。
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


# FastAPI 的依赖函数。路由参数写成 db: Session = Depends(get_db) 时会调用它。
def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求一个数据库会话。"""
    # 本次请求单独拿一个会话，请求之间不共用，避免互相看到未提交的数据。
    db = SessionLocal()
    try:
        # yield 把会话交给路由函数。路由函数返回后，才会执行 finally。
        yield db
    finally:
        # 无论成功、校验失败还是抛异常，都关闭会话，把连接还回连接池。
        db.close()
