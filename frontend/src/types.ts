// 前端自己的数据结构。字段名和后端 schemas.py 返回的 JSON 一致。
// 这里只描述形状，不包含请求函数。请求在 api.ts。

// 一条待办，对应后端的 TodoOut，也对应数据库表 todos。
export interface Todo {
  // 数据库自增主键。删除、改状态、改内容都用它。
  id: number
  // 待办正文。后端已经去掉首尾空格。
  content: string
  // true 表示已完成。已完成时页面会划线，并且不允许编辑内容。
  completed: boolean
  // 创建时间，ISO 时间字符串。显示前会交给 App.tsx 的 fmt 格式化。
  created_at: string
  // 最近一次修改时间。当前页面没有单独展示它。
  updated_at: string
  // 完成时间。未完成时后端返回 null，页面就不显示“完成于”。
  completed_at: string | null
}

// 一条操作流水，对应后端的 TodoLogOut，也对应表 todo_logs。
export interface TodoLog {
  // 流水自己的主键，不是待办 id。
  id: number
  // 这条记录属于哪一条待办。待办被删后，这个数字仍然留着。
  todo_id: number
  // 动作代号：create、update_content、complete、reopen、delete。
  // 页面上的中文标签由 App.tsx 的 ACTION_TEXT 翻译。
  action: string
  // 给人看的描述，例如“新建待办：买牛奶”。
  detail: string
  // 动作发生的时间。
  created_at: string
}

// 分页接口的通用外壳。T 是本页每一项的类型，列表接口里 T 是 Todo。
export interface PageResult<T> {
  // 当前这一页的记录，不是全部记录。
  items: T[]
  // 符合筛选条件的总条数。
  total: number
  // 当前页码，从 1 开始。
  page: number
  // 每页条数。后端字段是下划线 page_size，所以这里也用下划线。
  page_size: number
  // 总页数。没有数据时后端返回 0。
  pages: number
}

// GET /api/todos/stats 的结果，用来画三个筛选标签上的数字。
export interface Stats {
  // 全部待办数。
  total: number
  // 未完成数。
  pending: number
  // 已完成数。
  completed: number
}

// 筛选标签只允许这三个值，和后端的 StatusFilter 相同。
// all 全部，pending 未完成，completed 已完成。
export type StatusFilter = 'all' | 'pending' | 'completed'
