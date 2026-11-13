"""接口冒烟测试：用临时 SQLite 跑一遍增删改查与业务规则。

运行：python smoke_test.py
注意：仅用于本地验证，测试结束自动删除临时库文件。
"""

from __future__ import annotations

import os
import sys
import tempfile

TMP_DB = os.path.join(tempfile.gettempdir(), "todo_smoke_test.db")
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)

os.environ["DB_URL"] = f"sqlite:///{TMP_DB.replace(os.sep, '/')}"
os.environ["AUTO_CREATE_TABLES"] = "true"
os.environ["CORS_ORIGINS"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

failures: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}{(' -> ' + extra) if extra else ''}")
    if not cond:
        failures.append(name)


with TestClient(app) as client:
    # 健康检查 + 首页（dist 存在时应返回 html）
    r = client.get("/api/health")
    check("health", r.status_code == 200 and r.json()["status"] == "ok")

    r = client.get("/")
    check("index.html 可访问", r.status_code == 200)

    # 创建
    r = client.post("/api/todos", json={"content": "  写方案  "})
    check("新增待办", r.status_code == 201, r.text[:120])
    todo = r.json()
    todo_id = todo["id"]
    check("内容首尾空格被裁剪", todo["content"] == "写方案", repr(todo["content"]))
    check("默认未完成", todo["completed"] is False)

    # 空内容校验
    r = client.post("/api/todos", json={"content": "   "})
    check("空内容被拒绝", r.status_code == 422, str(r.status_code))

    # 再建两条
    client.post("/api/todos", json={"content": "买牛奶"})
    client.post("/api/todos", json={"content": "写周报"})

    # 列表 / 分页 / 搜索
    r = client.get("/api/todos", params={"page": 1, "page_size": 2})
    data = r.json()
    check("分页 page_size 生效", len(data["items"]) == 2 and data["total"] == 3, str(data["total"]))
    check("总页数正确", data["pages"] == 2, str(data["pages"]))

    r = client.get("/api/todos", params={"keyword": "牛奶"})
    check("关键词搜索", r.json()["total"] == 1)

    # 改内容（未完成可以改）
    r = client.patch(f"/api/todos/{todo_id}/content", json={"content": "写完整方案"})
    check("未完成可改内容", r.status_code == 200 and r.json()["content"] == "写完整方案")

    # 改状态：完成
    r = client.patch(f"/api/todos/{todo_id}/status", json={"completed": True})
    body = r.json()
    check("标记完成", r.status_code == 200 and body["completed"] is True)
    check("completed_at 已写入", body["completed_at"] is not None)

    # 已完成不能改内容
    r = client.patch(f"/api/todos/{todo_id}/content", json={"content": "偷偷改"})
    check("已完成禁止改内容(409)", r.status_code == 409, r.text[:120])

    # 取消完成 → 又能改
    r = client.patch(f"/api/todos/{todo_id}/status", json={"completed": False})
    check("取消完成", r.status_code == 200 and r.json()["completed"] is False)
    check("completed_at 已清空", r.json()["completed_at"] is None)
    r = client.patch(f"/api/todos/{todo_id}/content", json={"content": "取消后可改"})
    check("取消完成可改内容", r.status_code == 200)

    # 状态筛选
    client.patch(f"/api/todos/{todo_id}/status", json={"completed": True})
    r = client.get("/api/todos", params={"status": "completed"})
    check("按已完成筛选", r.json()["total"] == 1, str(r.json()["total"]))
    r = client.get("/api/todos", params={"status": "pending"})
    check("按未完成筛选", r.json()["total"] == 2, str(r.json()["total"]))

    # 统计
    r = client.get("/api/todos/stats")
    s = r.json()
    check("统计正确", s == {"total": 3, "pending": 2, "completed": 1}, str(s))

    # 历史流水
    r = client.get("/api/todos/logs")
    logs = r.json()
    actions = {item["action"] for item in logs}
    check("历史流水包含各类操作", {"create", "update_content", "complete", "reopen"} <= actions, str(actions))

    # 删除
    r = client.delete(f"/api/todos/{todo_id}")
    check("删除待办", r.status_code == 200)
    r = client.delete(f"/api/todos/{todo_id}")
    check("删除不存在返回 404", r.status_code == 404)
    r = client.get("/api/todos")
    check("删除后总数减少", r.json()["total"] == 2)

    # 不存在 id 的操作
    r = client.patch("/api/todos/99999/status", json={"completed": True})
    check("不存在 id 返回 404", r.status_code == 404)

    # SPA 兜底
    r = client.get("/some/deep/route")
    check("SPA 兜底返回 index.html", r.status_code == 200 and b"<div id=\"root\">" in r.content)
    r = client.get("/api/not-exist")
    check("未知 api 返回 404", r.status_code == 404)

print()
if failures:
    print("FAILED:", ", ".join(failures))
    sys.exit(1)
print("全部通过 ✅")
#  test