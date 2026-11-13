# 业务层：真正改数据库的地方。
# 路由层（routers/todos.py）只负责 HTTP；这里负责查到没有、能不能改、要不要记流水。
# 每个函数都接收一个 Session，自己决定什么时候 commit。
"""数据库操作层。"""

# 允许 str | None、list[models.TodoLog] 这种类型写法。
from __future__ import annotations

# math.ceil 用来把“总条数 / 每页条数”向上取整，得到总页数。
import math
# 完成时间用应用服务器的当前时间，而不是单独再写一条 SQL 的 NOW()。
from datetime import datetime

# func 提供 count() 这类 SQL 函数。select 用来构造 SELECT 语句。
from sqlalchemy import func, select
# Session 是一次数据库会话，由 database.get_db 注入进来。
from sqlalchemy.orm import Session

# models 是表，schemas 是接口入参/出参。本文件把两者接起来。
from . import models, schemas


# 待办 id 在数据库里不存在时抛出。路由层把它变成 HTTP 404。
class TodoNotFound(Exception):
    # 不增加字段，只用异常消息说明是哪一个 id。
    pass


# 已完成的待办还想改正文时抛出。路由层把它变成 HTTP 409。
class TodoAlreadyCompleted(Exception):
    """已完成的待办不允许修改内容。"""


# 内部函数：给某个待办追加一条流水。下划线开头表示只给本文件用。
def _log(db: Session, todo_id: int, action: str, detail: str) -> None:
    # 只是把 TodoLog 放进会话，这里不 commit。
    # 调用方会和待办本身的改动一起提交，这样两张表要么一起成功，要么一起失败。
    # detail[:500] 保证描述不会超过列的长度。
    db.add(models.TodoLog(todo_id=todo_id, action=action, detail=detail[:500]))


# 新建一条未完成的待办，并记一条 create 流水。
def create_todo(db: Session, payload: schemas.TodoCreate) -> models.Todo:
    # payload.content 此时已经被 schemas.py 去掉首尾空格。
    todo = models.Todo(content=payload.content, completed=False)
    # add 只是挂到会话上，还没有真正写库，所以还没有自增 id。
    db.add(todo)
    # flush 把 INSERT 发到数据库并取回 id，但不结束事务。
    # 下面写流水需要这个 id。
    db.flush()
    # 流水文案给历史面板看，例如“新建待办：买牛奶”。
    _log(db, todo.id, "create", f"新建待办：{todo.content}")
    # 待办和流水在同一个事务里提交。
    db.commit()
    # refresh 用数据库里的最终值回填对象，包括 created_at 等默认时间。
    db.refresh(todo)
    # 返回 ORM 对象。路由的 response_model 会把它转成 TodoOut。
    return todo


# 按主键取一条待办。找不到就抛 TodoNotFound，不返回 None。
def get_todo(db: Session, todo_id: int) -> models.Todo:
    # Session.get 是按主键查，等价于 SELECT ... WHERE id = todo_id。
    todo = db.get(models.Todo, todo_id)
    # 没有这一行时，把 id 写进错误信息，方便前端直接显示。
    if todo is None:
        raise TodoNotFound(f"待办 {todo_id} 不存在")
    return todo


# 分页查询。status、keyword 同时生效；结果先未完成、后已完成，新建的在前。
def list_todos(
    db: Session,
    # 星号后面的参数必须用名字传递，避免把筛选和页码的位置传错。
    *,
    # 默认查全部。只可能是 all / pending / completed，路由层已经限制过。
    status: schemas.StatusFilter = "all",
    # None 或空字符串表示不按内容搜索。
    keyword: str | None = None,
    # 页码从 1 开始。
    page: int = 1,
    # 默认每页 10 条，和前端 App.tsx 的 pageSize 一致。
    page_size: int = 10,
) -> schemas.PageResult[schemas.TodoOut]:
    # 收集 WHERE 条件。列表为空就表示不加过滤。
    conditions = []
    # pending 只留未完成。is_(False) 生成 SQL 的 completed = 0。
    if status == "pending":
        conditions.append(models.Todo.completed.is_(False))
    # completed 只留已完成。all 不加这个条件。
    elif status == "completed":
        conditions.append(models.Todo.completed.is_(True))
    # 关键字按内容模糊匹配。% 放在两边，所以是“包含”，不是“开头是”。
    if keyword:
        conditions.append(models.Todo.content.like(f"%{keyword.strip()}%"))

    # 一条语句只数总数，不把记录取回来。
    count_stmt = select(func.count()).select_from(models.Todo)
    # 另一条语句取当前页的记录。
    stmt = select(models.Todo)
    # 同一个条件同时加到计数和取数上，保证 total 和 items 口径一致。
    for cond in conditions:
        count_stmt = count_stmt.where(cond)
        stmt = stmt.where(cond)

    # scalar 取单个数字。没有任何行时可能是 None，这时当成 0。
    total = db.scalar(count_stmt) or 0
    # 页码最小是 1，避免 offset 变成负数。
    page = max(1, page)
    # 每页至少 1 条、最多 100 条。路由层也限制了 le=100，这里再挡一次。
    page_size = min(max(1, page_size), 100)

    # 排序：completed 升序，所以 false(0) 在前、true(1) 在后。
    # 同一状态里 created_at 降序，新建的在前；时间相同再按 id 降序。
    # offset 跳过前面的页，limit 只取本页。
    rows = db.scalars(
        stmt.order_by(models.Todo.completed.asc(), models.Todo.created_at.desc(), models.Todo.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    # 组装分页对象。items 先从 ORM 转成 TodoOut，避免把内部对象直接暴露出去。
    return schemas.PageResult[schemas.TodoOut](
        items=[schemas.TodoOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        # 有数据时向上取整。例如 11 条、每页 10 条，是 2 页。没有数据时页数是 0。
        pages=max(1, math.ceil(total / page_size)) if total else 0,
    )


# 修改正文。已完成的待办直接拒绝，内容没变则不记流水。
def update_content(db: Session, todo_id: int, payload: schemas.TodoUpdateContent) -> models.Todo:
    # 不存在会在 get_todo 里变成 TodoNotFound。
    todo = get_todo(db, todo_id)
    # 业务规则：已完成不能改内容。调用方需要先把状态改回未完成。
    if todo.completed:
        raise TodoAlreadyCompleted("已完成的待办不能修改内容，请先取消完成")
    # 先留下旧内容，流水里要写成“旧 -> 新”。
    old = todo.content
    # 改对象属性。真正的 UPDATE 要等 commit。
    todo.content = payload.content
    # 内容确实变了才写流水，避免相同内容点保存也多一条历史。
    if old != todo.content:
        _log(db, todo.id, "update_content", f"内容：{old} -> {todo.content}")
    # 提交待办更新和可能存在的流水。
    db.commit()
    # 重新读一次，拿到 onupdate 写入的 updated_at。
    db.refresh(todo)
    return todo


# 切换完成状态。状态没变时什么都不写。
def update_status(db: Session, todo_id: int, payload: schemas.TodoUpdateStatus) -> models.Todo:
    todo = get_todo(db, todo_id)
    # 重复点击同一个状态：不改 completed_at，也不追加流水。
    if todo.completed == payload.completed:
        return todo
    # 写入新状态。
    todo.completed = payload.completed
    # 变成完成时记下现在的时间；变回未完成时清空，前端就不再显示“完成于”。
    todo.completed_at = datetime.now() if payload.completed else None
    # 完成和取消完成用不同的 action，前端据此显示不同颜色的标签。
    _log(
        db,
        todo.id,
        "complete" if payload.completed else "reopen",
        "标记为已完成" if payload.completed else "取消完成",
    )
    # 状态和流水一起提交。
    db.commit()
    db.refresh(todo)
    return todo


# 删除待办。先写流水再删除，因为流水文案要用到正文。
def delete_todo(db: Session, todo_id: int) -> None:
    todo = get_todo(db, todo_id)
    # 流水不随待办删除。todo_logs 没有外键级联，所以删 todos 不会删掉历史。
    _log(db, todo.id, "delete", f"删除待办：{todo.content}")
    # 从会话里标记删除。和上面的 add 同一次 commit 才生效。
    db.delete(todo)
    db.commit()


# 统计三个数字，给页面标签角标用。不做分页。
def stats(db: Session) -> schemas.StatsOut:
    # 全部行数。
    total = db.scalar(select(func.count()).select_from(models.Todo)) or 0
    # 已完成行数。未完成不必再查一次。
    completed = db.scalar(
        select(func.count()).select_from(models.Todo).where(models.Todo.completed.is_(True))
    ) or 0
    # pending 用减法得到，保证三个数字加得齐。
    return schemas.StatsOut(total=total, pending=total - completed, completed=completed)


# 取最近的操作流水，按时间倒序。默认 50 条，上限 200 条。
def list_logs(db: Session, limit: int = 50) -> list[models.TodoLog]:
    # 把调用方传来的 limit 夹到 1 和 200 之间。
    limit = min(max(1, limit), 200)
    # scalars().all() 得到的是标量结果序列，转成 list 后返回。
    # 先按时间新的在前，时间相同再按流水 id 新的在前。
    return list(
        db.scalars(
            select(models.TodoLog).order_by(models.TodoLog.created_at.desc(), models.TodoLog.id.desc()).limit(limit)
        ).all()
    )
