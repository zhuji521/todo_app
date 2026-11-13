# HTTP 层：把 crud.py 的函数暴露成 REST 接口。
# 本文件决定路径、查询参数和状态码；业务规则仍在 crud.py。
# 注意 /stats、/logs 写在 /{todo_id} 前面，否则 "stats" 会被当成一个 id。
"""待办相关路由。"""

# 允许 list[schemas.TodoLogOut] 这种类型写法。
from __future__ import annotations

# APIRouter：一组接口，最后由 main.py include 进来。
# Depends：声明“调用这个函数前，先调用 get_db”。
# HTTPException：把业务异常转换成带状态码的 HTTP 错误。
# Query：声明 URL 查询参数的默认值和范围。
# status：HTTP 状态码常量，避免在代码里散落裸数字。
from fastapi import APIRouter, Depends, HTTPException, Query, status
# 每个请求注入的数据库会话类型。
from sqlalchemy.orm import Session

# crud 做业务，models 是表对象，schemas 是入参和出参。
from .. import crud, models, schemas
# get_db 每个请求生成一个会话，请求结束自动关闭。
from ..database import get_db

# 这组接口的公共前缀是 /api/todos。tags 用来在 /docs 里分组。
router = APIRouter(prefix="/api/todos", tags=["todos"])


# GET /api/todos?status=&keyword=&page=&page_size=
# response_model 让 FastAPI 按 PageResult[TodoOut] 过滤并序列化返回值。
@router.get("", response_model=schemas.PageResult[schemas.TodoOut], summary="分页查询待办（含历史记录）")
def read_todos(
    # status 不传时是 all。Query 的 description 会出现在接口文档里。
    status: schemas.StatusFilter = Query("all", description="all / pending / completed"),
    # keyword 可以不传。最长 100，比正文的 500 短，因为这只是搜索词。
    keyword: str | None = Query(None, max_length=100, description="内容模糊搜索"),
    # 页码至少为 1。小于 1 时 FastAPI 直接 422，不会进入函数。
    page: int = Query(1, ge=1),
    # 每页 1 到 100 条，默认 10。
    page_size: int = Query(10, ge=1, le=100),
    # Depends(get_db) 会先执行 get_db，把 yield 出来的 Session 传给 db。
    db: Session = Depends(get_db),
) -> schemas.PageResult[schemas.TodoOut]:
    # 参数原样交给业务层。分页和排序规则都在 list_todos 里。
    return crud.list_todos(db, status=status, keyword=keyword, page=page, page_size=page_size)


# GET /api/todos/stats，返回总数、未完成数、已完成数。
@router.get("/stats", response_model=schemas.StatsOut, summary="数量统计")
def read_stats(db: Session = Depends(get_db)) -> schemas.StatsOut:
    # 没有查询参数，直接统计整张 todos 表。
    return crud.stats(db)


# GET /api/todos/logs?limit=50，返回最近的操作流水。
@router.get("/logs", response_model=list[schemas.TodoLogOut], summary="操作历史流水")
def read_logs(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)) -> list[models.TodoLog]:
    # 函数返回 ORM 对象列表。response_model 会逐条转成 TodoLogOut 再输出 JSON。
    return crud.list_logs(db, limit=limit)


# POST /api/todos，请求体是 {"content": "..."}。成功时用 201，而不是默认的 200。
@router.post("", response_model=schemas.TodoOut, status_code=status.HTTP_201_CREATED, summary="新增待办")
def create_todo(payload: schemas.TodoCreate, db: Session = Depends(get_db)) -> models.Todo:
    # FastAPI 在进入函数前已经用 TodoCreate 校验并裁剪过 content。
    # 校验失败会自动 422，不会调用 create_todo。
    return crud.create_todo(db, payload)


# PATCH /api/todos/{todo_id}/status，请求体是 {"completed": true 或 false}。
@router.patch("/{todo_id}/status", response_model=schemas.TodoOut, summary="修改完成状态")
def update_status(
    # 路径里的数字会转成 int。不是数字时 FastAPI 返回 422。
    todo_id: int, payload: schemas.TodoUpdateStatus, db: Session = Depends(get_db)
) -> models.Todo:
    try:
        # 找到并更新。状态没有变化时，crud 会原样返回，不写流水。
        return crud.update_status(db, todo_id, payload)
    # 没有这条待办：404，detail 是“待办 x 不存在”。
    except crud.TodoNotFound as exc:
        # from exc 保留原来的异常链，方便日志里看到是谁引起的。
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# PATCH /api/todos/{todo_id}/content，请求体是 {"content": "..."}。
@router.patch("/{todo_id}/content", response_model=schemas.TodoOut, summary="修改内容（已完成不可改）")
def update_content(
    todo_id: int, payload: schemas.TodoUpdateContent, db: Session = Depends(get_db)
) -> models.Todo:
    try:
        return crud.update_content(db, todo_id, payload)
    # id 不存在。
    except crud.TodoNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # 待办已经完成。409 表示请求和当前资源状态冲突。
    except crud.TodoAlreadyCompleted as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# DELETE /api/todos/{todo_id}。成功时返回 {"message": "删除成功"}。
@router.delete("/{todo_id}", response_model=schemas.MessageOut, summary="删除待办")
def delete_todo(todo_id: int, db: Session = Depends(get_db)) -> schemas.MessageOut:
    try:
        # delete_todo 没有返回值。删除前它会先把“删除待办：...”写进流水。
        crud.delete_todo(db, todo_id)
    except crud.TodoNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # 走到这里说明删除已经提交。单独构造一个只含 message 的响应。
    return schemas.MessageOut(message="删除成功")
