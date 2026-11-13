# 接口的数据结构层，使用 Pydantic v2。
# 请求进来时，FastAPI 用这些类检查 JSON；响应出去时，用这些类决定返回哪些字段。
# 它和 models.py 的差别：models 对应数据库的表，schemas 对应 HTTP 的入参和出参。
"""请求 / 响应数据结构（Pydantic v2）。"""

# 允许 datetime | None、list[T] 这类写法。
from __future__ import annotations

# datetime 用来标注时间字段；真正的时间值来自数据库。
from datetime import datetime
# Generic、TypeVar 用来写“一页里面装任意类型”的 PageResult[T]。
# Literal 用来把一个字符串限制成几个固定值。
from typing import Generic, Literal, TypeVar

# BaseModel：一个 Pydantic 模型，能校验并转换输入。
# ConfigDict：模型的行为开关，这里用来允许从 ORM 对象读取字段。
# Field：给字段加长度、必填、说明。
# field_validator：在字段赋值之后再跑一段自己的检查。
from pydantic import BaseModel, ConfigDict, Field, field_validator

# T 是 PageResult 的占位类型。PageResult[TodoOut] 表示这一页装的是待办。
T = TypeVar("T")


# POST /api/todos 的请求体，只接收 content 一个字段。
class TodoCreate(BaseModel):
    # ... 表示必填。长度 1 到 500，和数据库 VARCHAR(500) 对齐。
    # 只含空格的字符串长度仍大于 0，所以还要靠下面的校验器拒绝。
    content: str = Field(..., min_length=1, max_length=500, description="待办内容")

    # 声明 content 在通过 Field 的检查之后，还要经过 strip_content。
    @field_validator("content")
    # 校验器写成类方法，第一个参数是类本身，不是某条待办。
    @classmethod
    def strip_content(cls, value: str) -> str:
        # 去掉首尾空格。前端也会 trim 一次，这里是后端自己的保证。
        value = value.strip()
        # 去掉空格后如果什么都不剩，校验失败。FastAPI 会返回 422。
        if not value:
            raise ValueError("内容不能为空")
        # 返回值会替换原来的 content，所以入库的是裁剪后的文本。
        return value


# PATCH /api/todos/{id}/content 的请求体。规则和新建相同，单独一个类是为了语义分开。
class TodoUpdateContent(BaseModel):
    # 同样限制 1 到 500 个字符。
    content: str = Field(..., min_length=1, max_length=500)

    # 和 TodoCreate 一样，保存前去掉首尾空格并拒绝空内容。
    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("内容不能为空")
        return value


# PATCH /api/todos/{id}/status 的请求体。只接收一个布尔值。
class TodoUpdateStatus(BaseModel):
    # true 表示标记完成，false 表示取消完成。
    completed: bool


# 返回给前端的一条待办。字段名和 models.Todo、前端 types.ts 的 Todo 对齐。
class TodoOut(BaseModel):
    # from_attributes=True：允许用 TodoOut.model_validate(orm对象) 从数据库对象拷贝字段。
    # 没有这个开关，Pydantic 只接受字典，不接受 SQLAlchemy 对象。
    model_config = ConfigDict(from_attributes=True)

    # 数据库生成的主键。
    id: int
    # 已裁剪过的正文。
    content: str
    # 是否完成。
    completed: bool
    # 下面三个时间由数据库/ORM 生成。完成时间可以是空。
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


# 返回给前端的一条操作流水。
class TodoLogOut(BaseModel):
    # 同样允许直接从 TodoLog 这个 ORM 对象转换。
    model_config = ConfigDict(from_attributes=True)

    # 流水主键。
    id: int
    # 关联的待办 id。待办被删后，这个数字仍然留在流水里。
    todo_id: int
    # create / update_content / complete / reopen / delete 之一。
    action: str
    # 给人读的描述。
    detail: str
    # 这条流水写入的时间。
    created_at: datetime


# 分页响应。T 由调用处决定，列表接口用的是 PageResult[TodoOut]。
class PageResult(BaseModel, Generic[T]):
    # 当前这一页的记录。
    items: list[T]
    # 符合筛选条件的总条数，不是本页条数。
    total: int
    # 当前页码，从 1 开始。
    page: int
    # 每页条数。
    page_size: int
    # 总页数。没有数据时 crud.py 会把它算成 0。
    pages: int


# GET /api/todos/stats 的响应，给页面上三个标签的角标用。
class StatsOut(BaseModel):
    # 全部待办数。
    total: int
    # 未完成数。crud.py 用 total - completed 算出来。
    pending: int
    # 已完成数。
    completed: int


# 删除成功时的响应。删除接口不返回被删的那条待办，只返回一句话。
class MessageOut(BaseModel):
    # 固定是“删除成功”，由路由层填入。
    message: str


# 列表筛选只允许这三个字符串。别的值 FastAPI 会直接返回 422，到不了 crud.py。
StatusFilter = Literal["all", "pending", "completed"]
