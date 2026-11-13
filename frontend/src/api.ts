// 接口层。页面不直接写 fetch，统一调用下面 api 对象上的方法。
// 每个方法对应后端 routers/todos.py 里的一个地址。

// 只导入类型，编译后这行会被擦掉，不会增加运行代码。
import type { PageResult, Stats, StatusFilter, Todo, TodoLog } from './types'

// 生产环境前后端同源，用相对路径即可；开发环境由 vite proxy 转发到 8000 端口。
// VITE_API_BASE 来自环境变量，类型在 vite-env.d.ts。没配置时用空字符串。
const BASE = import.meta.env.VITE_API_BASE ?? ''

// 把失败的请求统一包成这种错误。页面用 instanceof ApiError 判断后，直接显示 message。
export class ApiError extends Error {
  // HTTP 状态码。连不上服务器时约定为 0，因为那时还没有响应。
  status: number
  // message 给人看，status 给调用方判断是 409、404 还是网络断开。
  constructor(message: string, status: number) {
    // 先让 Error 记住 message，这样 e.message 可用。
    super(message)
    // 再把状态码存到自己身上。
    this.status = status
  }
}

// 所有接口共用的请求函数。T 是成功时 JSON 对应的类型。
// path 形如 /api/todos。init 用来额外指定 method、body。
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // 先声明响应变量。try 里赋值，try 外面还要接着判断状态码。
  let res: Response
  try {
    // BASE 通常是空的，所以实际请求的是 /api/...。
    // 默认带上 JSON 头。init 放在后面，调用方可以覆盖 method、body，也可以覆盖 headers。
    res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch {
    // fetch 只有在网络层失败时才抛异常，例如后端没开。HTTP 4xx/5xx 不会进这里。
    throw new ApiError('网络异常，无法连接后端服务', 0)
  }

  // ok 表示状态码在 200 到 299。422、404、409 都会进这个分支。
  if (!res.ok) {
    // 先准备一句兜底提示。如果响应体里有更具体的 detail，下面会换掉它。
    let detail = `请求失败（${res.status}）`
    try {
      // 后端错误格式是 {"detail": "..."}。校验失败时 detail 是一个数组。
      const data = await res.json()
      // 业务错误，例如“已完成的待办不能修改内容”。detail 是字符串。
      if (typeof data?.detail === 'string') detail = data.detail
      // 参数校验错误。FastAPI 返回 detail: [{ msg: "..." }]。取第一条的 msg。
      else if (Array.isArray(data?.detail) && data.detail[0]?.msg) detail = data.detail[0].msg
    } catch {
      /* 忽略解析失败 */
    }
    // 把整理好的文字和状态码一起抛出，页面的 catch 会显示它。
    throw new ApiError(detail, res.status)
  }

  // 204 没有响应体。当前这组接口没有用 204，这里是防御性处理，避免对空体调用 json()。
  if (res.status === 204) return undefined as T
  // 成功时把 JSON 当成调用方声明的类型。这里不做运行时校验。
  return (await res.json()) as T
}

// 列表查询的参数。pageSize 用驼峰，发给后端时会改成 page_size。
export interface ListQuery {
  // all、pending 或 completed。
  status: StatusFilter
  // 搜索词。空字符串表示不搜索。
  keyword: string
  // 页码，从 1 开始。
  page: number
  // 每页条数。页面里固定传 10。
  pageSize: number
}

// 页面实际调用的对象。每个方法返回一个 Promise，失败时抛 ApiError。
export const api = {
  // GET /api/todos。返回当前页的待办和分页信息。
  list(params: ListQuery): Promise<PageResult<Todo>> {
    // URLSearchParams 负责编码，并生成 status=all&page=1&page_size=10 这种查询串。
    const qs = new URLSearchParams({
      // 筛选状态，后端默认也是 all。
      status: params.status,
      // 查询串的值必须是字符串，所以数字要先转一下。
      page: String(params.page),
      // 后端参数名是下划线 page_size，不是前端的 pageSize。
      page_size: String(params.pageSize),
    })
    // 有实际内容才带 keyword。只有空格时 trim 后为空，不传这个参数。
    if (params.keyword.trim()) qs.set('keyword', params.keyword.trim())
    // 拼成 /api/todos?status=all&page=1&page_size=10。
    return request<PageResult<Todo>>(`/api/todos?${qs.toString()}`)
  },
  // GET /api/todos/stats。给三个标签上的数字用。
  stats(): Promise<Stats> {
    return request<Stats>('/api/todos/stats')
  },
  // GET /api/todos/logs。limit 默认 30，和页面右侧“最近 30 条”一致。
  logs(limit = 30): Promise<TodoLog[]> {
    // limit 直接拼进查询串。后端还会再把它限制在 1 到 200。
    return request<TodoLog[]>(`/api/todos/logs?limit=${limit}`)
  },
  // POST /api/todos。成功时返回新建的那一条。
  create(content: string): Promise<Todo> {
    // method 不写时 fetch 默认是 GET，所以这里必须写 POST。
    // body 要是字符串，JSON.stringify 把 { content } 变成 '{"content":"..."}'。
    return request<Todo>('/api/todos', { method: 'POST', body: JSON.stringify({ content }) })
  },
  // PATCH /api/todos/{id}/content。已完成的待办后端会返回 409。
  updateContent(id: number, content: string): Promise<Todo> {
    return request<Todo>(`/api/todos/${id}/content`, {
      // PATCH 表示只改资源的一部分，这里只改正文。
      method: 'PATCH',
      body: JSON.stringify({ content }),
    })
  },
  // PATCH /api/todos/{id}/status。completed 为 true 是完成，false 是取消完成。
  updateStatus(id: number, completed: boolean): Promise<Todo> {
    return request<Todo>(`/api/todos/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ completed }),
    })
  },
  // DELETE /api/todos/{id}。成功时后端返回 { message: "删除成功" }。
  remove(id: number): Promise<{ message: string }> {
    return request<{ message: string }>(`/api/todos/${id}`, { method: 'DELETE' })
  },
}
