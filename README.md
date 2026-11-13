# 待办清单（Todo List）

React + FastAPI + MySQL 的全栈待办清单：支持**增、删、改内容、改状态、查（分页/搜索/筛选）**，
并保留完整**操作历史记录**；前端打包成 `index.html + static/` 放进后端目录，整体用 Docker 持久化运行。

```
todo-app/
├── frontend/                 # 前端源码（React 18 + TypeScript + Vite）
│   ├── src/
│   │   ├── App.tsx           # 页面与全部交互
│   │   ├── api.ts            # 后端接口封装
│   │   ├── types.ts          # 类型定义
│   │   ├── styles.css        # 样式
│   │   └── main.tsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts        # 关键：打包输出到 ../backend/dist，资源目录 static
├── backend/                  # 后端（FastAPI + SQLAlchemy 2.0）
│   ├── app/
│   │   ├── main.py           # 应用入口 + 静态站点托管 + SPA 兜底
│   │   ├── config.py         # 全部配置（环境变量 / .env）
│   │   ├── database.py       # 引擎、会话、Base
│   │   ├── models.py         # ORM 模型：todos / todo_logs
│   │   ├── schemas.py        # Pydantic 出入参校验
│   │   ├── crud.py           # 业务逻辑（含"已完成不能改内容"规则）
│   │   └── routers/todos.py  # REST 路由
│   ├── sql/
│   │   ├── init.sql          # 建库 + 建账号 + 建表（可重复执行）
│   │   └── create_database.sql
│   ├── dist/                 # ★ 前端打包产物（index.html + static/）
│   ├── logs/                 # 运行日志（app.log，滚动 5MB×3）
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── .env.example
│   └── smoke_test.py         # 26 项接口冒烟测试
├── docker-compose.yml        # mysql + api 两个服务，数据卷持久化
├── .env.example
└── README.md
```

---

## 一、功能说明

| 需求 | 实现 |
| --- | --- |
| 新增待办 | `POST /api/todos`，内容自动裁剪首尾空格，空内容 422 拒绝 |
| 改状态（未完成 ↔ 已完成） | `PATCH /api/todos/{id}/status`，完成时写入 `completed_at`，取消时清空 |
| 改内容（**已完成不可改**） | `PATCH /api/todos/{id}/content`，已完成返回 **409**，前端"编辑"按钮同时置灰 |
| 删除 | `DELETE /api/todos/{id}`，带二次确认 |
| 查 | `GET /api/todos` 支持 `status` 筛选、`keyword` 模糊搜索、`page/page_size` 分页；未完成优先、新建在前 |
| 历史记录 | 每次操作写 `todo_logs` 流水，`GET /api/todos/logs` 返回最近 N 条，页面右侧时间轴展示 |
| 统计 | `GET /api/todos/stats` 返回总数/未完成/已完成，用于标签页角标 |

> 历史记录之所以是"真正入库"的：删掉待办后流水仍然保留，可以追溯"什么时候删了什么"。

---

## 二、本地数据库建库建表

### 1. 建库、建账号、建表（一条命令）

Windows（PowerShell / CMD，在项目根目录执行）：

```bash
mysql -u root -p"你的root密码" < backend\sql\init.sql
```

Linux / macOS：

```bash
mysql -u root -p < backend/sql/init.sql
```

`init.sql` 会做四件事，并且**可以重复执行**（全部 `IF NOT EXISTS`，不会清数据）：

1. 建库 `todo_db`（`utf8mb4` / `utf8mb4_unicode_ci`，支持中文和 emoji）
2. 建业务账号 `todo` / `todo_pass_123`（应用不要用 root 连库）
3. 建表 `todos`、`todo_logs`
4. 打印 `SHOW TABLES` 结果供核对

### 2. 验证

```bash
mysql -u todo -p"todo_pass_123" -D todo_db -e "SHOW TABLES; DESC todos;"
```

应看到 `todos` 与 `todo_logs` 两张表。表结构：

```sql
CREATE TABLE `todos` (
    `id`           INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `content`      VARCHAR(500) NOT NULL,
    `completed`    TINYINT(1)   NOT NULL DEFAULT 0,
    `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `completed_at` DATETIME     NULL DEFAULT NULL,
    PRIMARY KEY (`id`),
    KEY `idx_completed` (`completed`),
    KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 3. 可视化工具（可选）

用 Navicat / DBeaver / Workbench 连 `127.0.0.1:3306`，账号 `todo`，即可看到数据。
（Docker 部署后数据库映射在 `127.0.0.1:3307`，见第五节。）

---

## 三、本地运行

### 1. 后端

```bash
cd backend
python -m venv .venv

# Windows
.\.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env      # Linux: cp .env.example .env
# 编辑 .env，把 DB_PASSWORD 改成你实际的密码

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- 接口文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

打开 <http://127.0.0.1:5173>。

开发环境不用配跨域：`vite.config.ts` 里已把 `/api` 代理到 `http://127.0.0.1:8000`。

### 3. 一次性自检（可选但推荐）

不依赖 MySQL 也能跑，用临时 SQLite 验证全部业务规则：

```bash
cd backend
python smoke_test.py
```

输出 26 个 `[PASS]` 与 `全部通过 ✅` 即正常。

---

## 四、打包与"单端口部署验证"

```bash
cd frontend
npm run build
```

产物直接落到 `backend/dist/`：

```
backend/dist/
├── index.html
└── static/
    ├── index-xxxx.css
    └── index-xxxx.js
```

然后**只启动后端**（不要开 `npm run dev`）：

```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

访问 <http://127.0.0.1:8000> 就是完整应用 —— 此时前后端同源，没有跨域问题。

要点说明：

- `vite.config.ts` 的 `base: './'`：`index.html` 里引用 `./static/xxx`，放到任意路径都能跑
- `assetsDir: 'static'`：确保资源统一进 `static/`
- `main.py` 挂载了 `/static`，并加了 SPA 兜底路由（`/{full_path:path}`），刷新任意前端路由不会 404
- 兜底路由对 `/api/*` 明确返回 JSON 404，不会被误吞成 HTML

---

## 五、Docker 持久化部署（Linux 服务器）

### 1. 前置

服务器装好 Docker 与 Compose 插件：

```bash
docker --version
docker compose version
```

### 2. 上传项目

把**整个项目目录**（含已打包的 `backend/dist`）传到服务器，例如 `/opt/todo-app`：

```bash
# 本地执行
scp -r todo-app user@your-server:/opt/
```

> 也可以在服务器上现打包：进入 `frontend` 执行 `npm ci && npm run build`，
> 产物同样会进 `backend/dist`。

### 3. 配置密码

```bash
cd /opt/todo-app
cp .env.example .env
vi .env          # 改掉 MYSQL_ROOT_PASSWORD / DB_PASSWORD
```

### 4. 启动

```bash
docker compose up -d --build
docker compose ps
```

看到 `todo-mysql` 为 `healthy`、`todo-api` 为 `running` 即成功。

访问 `http://<服务器IP>:8000`。

### 5. 持久化是怎么做的

| 内容 | 位置 | 说明 |
| --- | --- | --- |
| MySQL 数据 | 命名卷 `mysql_data` → `/var/lib/mysql` | `docker compose down` / 重启机器都不丢；只有 `down -v` 才删 |
| 建表脚本 | `./backend/sql/init.sql` 挂到 `/docker-entrypoint-initdb.d/` | 数据卷**首次**创建时自动建表；卷已存在则跳过（不覆盖数据） |
| 前端产物 | `./backend/dist` → `/app/dist:ro` | 换前端包只需覆盖 `dist` 再 `restart api`，不必重新 build 镜像 |
| 应用日志 | `./backend/logs` → `/app/logs` | `app.log` 滚动 5MB × 3，宿主机可直接看 |

容器 `restart: always`，服务器重启后应用自动拉起。

### 6. 常用运维命令

```bash
docker compose logs -f api            # 跟踪后端日志
docker compose logs -f mysql          # 跟踪数据库日志
tail -f backend/logs/app.log          # 宿主机看应用日志

docker compose restart api            # 只重启后端（换了 dist 后执行）
docker compose up -d --build api      # 后端代码改动后重建

# 进库看数据（注意宿主机端口是 3307）
docker compose exec mysql mysql -utodo -ptodo_pass_123 -D todo_db -e "SELECT * FROM todos;"

# 备份数据库（强烈建议配 crontab 定时）
docker compose exec -T mysql mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction todo_db > backup_$(date +%F).sql

# 恢复
docker compose exec -T mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" todo_db < backup_2026-11-10.sql
```

### 7. 升级流程（代码有改动时）

```bash
cd /opt/todo-app
git pull                     # 或重新 scp
cd frontend && npm ci && npm run build && cd ..
docker compose up -d --build
```

数据库在数据卷里，升级不会影响已有数据。

---

## 六、接口一览

| 方法 | 路径 | 说明 | 主要参数 |
| --- | --- | --- | --- |
| GET | `/api/health` | 健康检查 | - |
| GET | `/api/todos` | 分页查询 | `status=all\|pending\|completed`、`keyword`、`page`、`page_size` |
| GET | `/api/todos/stats` | 数量统计 | - |
| GET | `/api/todos/logs` | 历史操作流水 | `limit`（1~200，默认 50） |
| POST | `/api/todos` | 新增 | body `{"content": "..."}` |
| PATCH | `/api/todos/{id}/status` | 改状态 | body `{"completed": true}` |
| PATCH | `/api/todos/{id}/content` | 改内容（已完成→409） | body `{"content": "..."}` |
| DELETE | `/api/todos/{id}` | 删除 | - |

响应示例：

```json
{
  "items": [
    {
      "id": 1,
      "content": "写项目方案",
      "completed": false,
      "created_at": "2026-11-10T16:24:19.837787",
      "updated_at": "2026-11-10T16:24:19.837787",
      "completed_at": null
    }
  ],
  "total": 1, "page": 1, "page_size": 10, "pages": 1
}
```

错误统一走 `{"detail": "..."}`，前端 `api.ts` 会取出来直接提示。

---

## 七、配置项（全部可用环境变量覆盖）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DB_HOST` | `127.0.0.1` | 数据库地址（容器内为 `mysql`） |
| `DB_PORT` | `3306` | 数据库端口 |
| `DB_USER` | `todo` | 数据库账号 |
| `DB_PASSWORD` | `todo_pass_123` | 数据库密码 |
| `DB_NAME` | `todo_db` | 库名 |
| `DB_URL` | 空 | 直接给完整连接串，填了则忽略上面几项（如 `sqlite:///./x.db`） |
| `AUTO_CREATE_TABLES` | `true` | 启动时自动建表（表已存在不会改结构） |
| `CORS_ORIGINS` | 空 | 逗号分隔的允许来源；前后端同源部署留空即可 |

时间统一由后端 Python 侧生成，容器内 `TZ=Asia/Shanghai`，避免"数据库时区 vs 服务器时区"导致的时间错乱。

---

## 八、已验证项

在 Windows 本地（Node 24 / Python 3.14 / Vite 6）实际跑过：

- `npm run build` 成功，产物为 `backend/dist/index.html + static/`
- `python smoke_test.py` 26 项全部 PASS，覆盖：空内容拒绝、首尾空格裁剪、分页、搜索、状态筛选、统计、
  **已完成禁止改内容（409）**、取消完成后可改、`completed_at` 写入与清空、404 分支、SPA 兜底、未知 api 404
- 浏览器实测：新增 → 勾选完成（"编辑"按钮自动置灰、`completed_at` 显示）→ 取消完成 → 改内容 → 删除，
  右侧历史时间轴逐步累积、时间显示为本地时区
