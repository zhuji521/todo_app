// 整页界面和交互都在这一个组件里。
// 数据来自 api.ts，类型来自 types.ts，外观来自 styles.css。

// useState 保存会变化的数据。数据一变，React 就按新数据重新画页面。
// useEffect 在渲染之后做请求、定时器这类副作用。
// useCallback 把函数记住，避免每次渲染都生成一个新函数。
// useMemo 把计算结果记住，只有依赖变了才重算。
// useRef 保存一个跨渲染还在的值，改它不会导致页面重画。这里用来记提示条的定时器。
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
// ApiError 是接口失败时抛出的错误。api 是全部请求方法。
import { ApiError, api } from './api'
// 只导入类型。Stats 是统计，StatusFilter 是筛选值，Todo 是一条待办，TodoLog 是一条流水。
import type { Stats, StatusFilter, Todo, TodoLog } from './types'

// 后端流水的 action 是英文代号，页面上要显示中文。
// Record<string, string> 表示“任意字符串键，对应一个中文字符串”。
const ACTION_TEXT: Record<string, string> = {
  // 新建待办。
  create: '新建',
  // 修改正文。
  update_content: '改内容',
  // 标记完成。
  complete: '完成',
  // 从已完成改回未完成。
  reopen: '取消完成',
  // 删除。流水还在，待办本身已经没了。
  delete: '删除',
}

// 把后端的 ISO 时间字符串格式化成“年-月-日 时:分”。没有时间或解析失败时有兜底。
function fmt(iso: string | null): string {
  // 未完成的 completed_at 是 null，页面上用短横线占位。当前调用处对 null 会先判断，这里再挡一次。
  if (!iso) return '-'
  // 按浏览器本地时区解析。后端存的是上海时间的无时区字符串，浏览器会按本地时区理解。
  const d = new Date(iso)
  // 无法解析时不要显示 Invalid Date，把原始字符串原样返回。
  if (Number.isNaN(d.getTime())) return iso
  // 月份、日期、小时、分钟都补成两位。
  const p = (n: number) => String(n).padStart(2, '0')
  // getMonth() 从 0 开始，所以要加 1。不显示秒。
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// 默认导出这个组件。main.tsx 用 <App /> 挂到页面上。
export default function App() {
  // 当前这一页的待办。不是数据库里的全部，只是本次查询返回的 items。
  const [todos, setTodos] = useState<Todo[]>([])
  // 三个标签的数量。初始先显示 0，等统计接口返回后再替换。
  const [stats, setStats] = useState<Stats>({ total: 0, pending: 0, completed: 0 })
  // 右侧历史，最近 30 条。
  const [logs, setLogs] = useState<TodoLog[]>([])

  // 当前筛选。all 全部，pending 未完成，completed 已完成。
  const [status, setStatus] = useState<StatusFilter>('all')
  // 搜索框里正在打的字。每敲一个键都更新它，但不会立刻请求。
  const [keywordInput, setKeywordInput] = useState('')
  // 真正拿去请求的关键词。由下面的防抖效果在停手约 350 毫秒后写入。
  const [keyword, setKeyword] = useState('')
  // 当前页码，从 1 开始。
  const [page, setPage] = useState(1)
  // 每页固定 10 条。这里没有 setPageSize，因为页面不提供修改每页条数。
  const [pageSize] = useState(10)
  // 总页数，由列表接口返回。0 表示当前筛选下没有数据。
  const [pages, setPages] = useState(0)
  // 符合条件的总条数，显示在列表头的“共 N 条”。
  const [total, setTotal] = useState(0)

  // 顶部输入框的内容，还没提交。
  const [newContent, setNewContent] = useState('')
  // 正在编辑的待办 id。null 表示现在没有一行处于编辑状态。
  const [editingId, setEditingId] = useState<number | null>(null)
  // 编辑框里的草稿。进入编辑时从那条待办的 content 复制过来。
  const [editingText, setEditingText] = useState('')
  // 正在提交的那条待办。非 null 时，这一行的勾选、编辑、删除会暂时禁用，避免重复点击。
  const [busyId, setBusyId] = useState<number | null>(null)
  // 列表是否正在加载。为 true 时列表头显示“加载中”，空列表时先不显示“暂无数据”。
  const [loading, setLoading] = useState(false)
  // 底部提示条。null 表示不显示。type 决定绿色成功还是红色失败的样式。
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)
  // 记住提示条的自动关闭定时器。用 ref 是因为换定时器不需要重新渲染。
  const toastTimer = useRef<number | null>(null)

  // 显示一条提示，并在 2.6 秒后关掉。连续触发时，先清掉上一个定时器，避免旧提示提前把新提示关掉。
  const showToast = useCallback((type: 'ok' | 'err', text: string) => {
    // 立刻画出提示。
    setToast({ type, text })
    // 如果上一条还在倒计时，取消它。
    if (toastTimer.current) window.clearTimeout(toastTimer.current)
    // window.setTimeout 返回数字 id。用 window. 是为了拿到浏览器的数字 id，而不是 NodeJS.Timeout。
    toastTimer.current = window.setTimeout(() => setToast(null), 2600)
  }, [])

  // 搜索框输入防抖
  // keywordInput 每变一次就重新计时。用户连续打字时，只有停顿超过 350 毫秒才真正搜索。
  useEffect(() => {
    const t = window.setTimeout(() => {
      // 把输入框的值交给真正的查询词。loadList 依赖 keyword，所以接着会重新请求。
      setKeyword(keywordInput)
      // 搜索词变了就回到第 1 页，避免还停在旧结果的后面几页。
      setPage(1)
    }, 350)
    // 下次输入，或组件卸载时，取消还没到点的定时器。
    return () => window.clearTimeout(t)
  }, [keywordInput])

  // 拉当前筛选、关键词、页码对应的一页待办。
  const loadList = useCallback(async () => {
    // 请求开始。列表头会显示“加载中”。
    setLoading(true)
    try {
      // 参数名在 api.list 内部会转换成后端要的 page_size。
      const data = await api.list({ status, keyword, page, pageSize })
      // 用这一页的记录替换列表。
      setTodos(data.items)
      // 记下总页数和总条数，分页按钮和“共 N 条”都用它们。
      setPages(data.pages)
      setTotal(data.total)
      // 删除最后一页最后一条后自动回退一页
      // 当前页被删空、而且不是第 1 页时，页码减 1。页码一变，本函数会因依赖变化再跑一次。
      if (data.items.length === 0 && page > 1) setPage(page - 1)
    } catch (e) {
      // 接口层把后端的 detail 放进 ApiError.message。其他异常用一句固定提示。
      showToast('err', e instanceof ApiError ? e.message : '加载列表失败')
    } finally {
      // 成功或失败都要结束加载状态，否则“加载中”会一直留着。
      setLoading(false)
    }
  }, [status, keyword, page, pageSize, showToast])

  // 拉右侧用的统计和历史。这两个请求互不依赖，所以并行发出。
  const loadSide = useCallback(async () => {
    try {
      // Promise.all 等两个都成功才继续。任何一个失败都会进 catch。
      const [s, l] = await Promise.all([api.stats(), api.logs(30)])
      // s 是 { total, pending, completed }，l 是流水数组。
      setStats(s)
      setLogs(l)
    } catch {
      /* 侧栏失败不阻塞主流程 */
    }
  }, [])

  // loadList 的身份变化时重新拉列表。筛选、关键词、页码变化都会让它变成新函数。
  useEffect(() => {
    // void 表示故意不等待这个 Promise，避免编辑器提示“有一个没人处理的 Promise”。
    void loadList()
  }, [loadList])

  // loadSide 的依赖是空数组，所以函数身份不变，这里只会在首次渲染后执行一次。
  // 之后要更新侧栏，靠下面的 refreshAll 主动再调一次。
  useEffect(() => {
    void loadSide()
  }, [loadSide])

  // 新增、修改、删除之后同时刷新列表和侧栏。
  const refreshAll = useCallback(() => {
    void loadList()
    void loadSide()
  }, [loadList, loadSide])

  // 提交顶部的“添加”表单。参数是表单的提交事件。
  async function handleCreate(e: React.FormEvent) {
    // 阻止浏览器默认提交。否则页面会整页刷新，组件状态就丢了。
    e.preventDefault()
    // 再去掉首尾空格。后端也会做同样的事，这里提前挡住空内容。
    const content = newContent.trim()
    // 空内容直接返回。按钮本身在内容为空时也是禁用的。
    if (!content) return
    try {
      // 发给 POST /api/todos。
      await api.create(content)
      // 成功后清空输入框，方便继续加下一条。
      setNewContent('')
      showToast('ok', '已添加')
      // 不在第 1 页时先把页码改回 1。页码变化会让 loadList 再按第 1 页请求一次。
      if (page !== 1) setPage(1)
      // 立刻按当前这次渲染里的筛选和页码刷新。侧栏的数量和历史也会更新。
      refreshAll()
    } catch (e) {
      // 422 时 message 是后端的“内容不能为空”或其他校验说明。
      showToast('err', e instanceof ApiError ? e.message : '添加失败')
    }
  }

  // 勾选或取消勾选。传进去的是这一行的待办。
  async function handleToggle(todo: Todo) {
    // 先锁住这一行，防止完成请求还没回来时又点删除或再次勾选。
    setBusyId(todo.id)
    try {
      // 把当前状态取反。已完成则传 false，未完成则传 true。
      await api.updateStatus(todo.id, !todo.completed)
      // 提示文案按点击前的状态决定。
      showToast('ok', todo.completed ? '已取消完成' : '已完成')
      // 列表里的完成时间和侧栏流水都要重新取。
      refreshAll()
    } catch (e) {
      showToast('err', e instanceof ApiError ? e.message : '操作失败')
    } finally {
      // 无论成功失败都解锁。不解锁的话这一行会一直不能点。
      setBusyId(null)
    }
  }

  // 进入编辑。已完成的待办在按钮上已经禁用，这里再判断一次，防止别的入口调进来。
  function startEdit(todo: Todo) {
    if (todo.completed) {
      showToast('err', '已完成的待办不能修改内容')
      return
    }
    // 记下哪一行在编辑。其他行仍显示普通文本。
    setEditingId(todo.id)
    // 用当前正文填进输入框，用户是在原文上改，不是从空白开始。
    setEditingText(todo.content)
  }

  // 保存编辑。todo 是进入编辑时的那一条，用来比较 id 和旧内容。
  async function saveEdit(todo: Todo) {
    const content = editingText.trim()
    // 删光内容不允许保存。后端也会拒绝空字符串。
    if (!content) {
      showToast('err', '内容不能为空')
      return
    }
    // 文字没有变化就退出编辑，不发请求，也不记一条流水。
    if (content === todo.content) {
      setEditingId(null)
      return
    }
    setBusyId(todo.id)
    try {
      // 发给 PATCH /api/todos/{id}/content。已完成时后端返回 409。
      await api.updateContent(todo.id, content)
      // 成功后收起输入框。
      setEditingId(null)
      showToast('ok', '已保存')
      refreshAll()
    } catch (e) {
      // 409 的 message 是“已完成的待办不能修改内容，请先取消完成”。
      showToast('err', e instanceof ApiError ? e.message : '保存失败')
    } finally {
      setBusyId(null)
    }
  }

  // 删除。先问一句，确认后才请求。
  async function handleDelete(todo: Todo) {
    // confirm 返回 false 表示用户点了取消。什么都不做。
    if (!window.confirm(`确认删除「${todo.content}」？`)) return
    setBusyId(todo.id)
    try {
      await api.remove(todo.id)
      showToast('ok', '已删除')
      // 列表会少一条。如果这一页因此变空，loadList 里会把页码退回上一页。
      // 侧栏仍能看到“删除待办：...”这句流水。
      refreshAll()
    } catch (e) {
      showToast('err', e instanceof ApiError ? e.message : '删除失败')
    } finally {
      setBusyId(null)
    }
  }

  // 三个筛选标签。数量来自 stats，所以 stats 变化时才重新生成这个数组。
  const tabs = useMemo(
    () =>
      [
        // key 是发给后端的 status。label 是按钮文字。count 是角标。
        { key: 'all' as StatusFilter, label: '全部', count: stats.total },
        { key: 'pending' as StatusFilter, label: '未完成', count: stats.pending },
        { key: 'completed' as StatusFilter, label: '已完成', count: stats.completed },
      ] satisfies { key: StatusFilter; label: string; count: number }[],
    // 只有统计数字变了才需要重算。
    [stats],
  )

  // 下面开始是页面结构。className 对应 styles.css 里的类。
  return (
    // 整页容器，限制最大宽度并居中。
    <div className="app">
      {/* 标题区。subtitle 只是说明文字，不参与交互。 */}
      <header className="topbar">
        <h1>待办清单</h1>
        <p className="subtitle">React + FastAPI + MySQL · 数据实时入库并保留历史记录</p>
      </header>

      {/* 左边是待办，右边是历史。窄屏时 styles.css 会把它们改成上下排列。 */}
      <main className="layout">
        {/* 左侧主卡片。 */}
        <section className="card main-card">
          {/* 添加表单。回车和点击“添加”都走 handleCreate。 */}
          <form className="create-row" onSubmit={handleCreate}>
            <input
              // 普通输入框样式。
              className="input"
              placeholder="输入待办内容，回车添加…"
              // 与后端 VARCHAR(500) 对齐，多打的字进不了输入框。
              maxLength={500}
              // 受控输入：显示的值永远等于 newContent。
              value={newContent}
              // 每敲一个键就更新 newContent，从而更新按钮是否可点。
              onChange={(e) => setNewContent(e.target.value)}
            />
            {/* 去掉空格后没内容就禁用。type="submit" 让回车也能触发表单。 */}
            <button className="btn btn-primary" type="submit" disabled={!newContent.trim()}>
              添加
            </button>
          </form>

          {/* 筛选标签和搜索框在同一行，窄了会换行。 */}
          <div className="toolbar">
            <div className="tabs">
              {/* tabs 有三项：全部、未完成、已完成。 */}
              {tabs.map((t) => (
                <button
                  // key 用筛选值，三项是稳定的。
                  key={t.key}
                  // 当前筛选项加上 active，样式会变成白底。
                  className={`tab ${status === t.key ? 'active' : ''}`}
                  onClick={() => {
                    // 切换筛选。
                    setStatus(t.key)
                    // 换筛选后从第 1 页看，避免新结果没有那么多页。
                    setPage(1)
                  }}
                >
                  {/* 文字，例如“未完成”。 */}
                  {t.label}
                  {/* 角标数字，来自统计接口。 */}
                  <span className="tab-count">{t.count}</span>
                </button>
              ))}
            </div>
            <input
              // 同时使用 input 和 search。search 把宽度限制在大约 220 像素。
              className="input search"
              placeholder="搜索内容…"
              // 绑定的是未防抖的输入。真正的请求看 keyword。
              value={keywordInput}
              onChange={(e) => setKeywordInput(e.target.value)}
            />
          </div>

          {/* 列表头：左边是数量和加载状态，右边是手动刷新。 */}
          <div className="list-head">
            <span>
              共 {total} 条{loading ? ' · 加载中…' : ''}
            </span>
            {/* 不改变筛选和页码，只把列表和侧栏再请求一次。 */}
            <button className="btn btn-ghost btn-sm" onClick={refreshAll}>
              刷新
            </button>
          </div>

          {/* 待办列表。没有项目符号，分隔线由 CSS 画。 */}
          <ul className="todo-list">
            {/* 请求已经结束、而且这一页没有数据时，才显示空状态。 */}
            {todos.length === 0 && !loading && (
              <li className="empty">暂无数据{keyword ? '，换个关键词试试' : '，先添加一条吧'}</li>
            )}
            {/* 把当前页的每条待办画成一行。 */}
            {todos.map((todo) => {
              // 这一行是不是正在编辑。同一时间只有 editingId 对应的那一行为 true。
              const editing = editingId === todo.id
              // 这一行是不是正在等接口。为 true 时勾选和两个按钮都禁用。
              const busy = busyId === todo.id
              return (
                // done 类让正文出现删除线，样式在 .todo-item.done .text。
                <li key={todo.id} className={`todo-item ${todo.completed ? 'done' : ''}`}>
                  {/* label 包住隐藏的 checkbox 和画出来的方框，点方框就等于点输入框。 */}
                  <label className="check">
                    <input
                      type="checkbox"
                      // 勾选状态完全由数据决定，不让输入框自己记状态。
                      checked={todo.completed}
                      // 请求进行中时不能再次切换。
                      disabled={busy}
                      // onChange 需要一个函数。void 同样是为了明确不等待这个异步函数。
                      onChange={() => void handleToggle(todo)}
                    />
                    {/* 真正看得见的方框。勾选后的对勾由 CSS 的 ::after 画出来。 */}
                    <span className="box" />
                  </label>

                  {/* 中间：正文或编辑框，下面是创建时间和完成时间。 */}
                  <div className="content">
                    {/* 编辑中显示输入框，否则显示文本。 */}
                    {editing ? (
                      <div className="edit-row">
                        <input
                          className="input"
                          // 进入编辑时自动聚焦，用户可以马上打字。
                          autoFocus
                          maxLength={500}
                          value={editingText}
                          onChange={(e) => setEditingText(e.target.value)}
                          onKeyDown={(e) => {
                            // 回车保存。Escape 放弃修改，不发请求。
                            if (e.key === 'Enter') void saveEdit(todo)
                            if (e.key === 'Escape') setEditingId(null)
                          }}
                        />
                        <button className="btn btn-primary btn-sm" onClick={() => void saveEdit(todo)}>
                          保存
                        </button>
                        {/* 取消只退出编辑，草稿被丢掉，正文保持原样。 */}
                        <button className="btn btn-ghost btn-sm" onClick={() => setEditingId(null)}>
                          取消
                        </button>
                      </div>
                    ) : (
                      // 普通显示。已完成时由 .done .text 加删除线。
                      <span className="text">{todo.content}</span>
                    )}
                    {/* 次要信息：创建时间、完成时间、编号。 */}
                    <div className="meta">
                      <span>创建 {fmt(todo.created_at)}</span>
                      {/* 只有完成过才有 completed_at。取消完成后后端会把它清成 null。 */}
                      {todo.completed_at && <span className="ok">完成 {fmt(todo.completed_at)}</span>}
                      <span className="id">#{todo.id}</span>
                    </div>
                  </div>

                  {/* 右侧操作。编辑和删除互不替代：完成的待办仍可删除。 */}
                  <div className="actions">
                    <button
                      className="btn btn-ghost btn-sm"
                      // 已完成或这一行正在请求时，不能进入编辑。
                      disabled={todo.completed || busy}
                      // 鼠标悬停说明为什么不能编辑。
                      title={todo.completed ? '已完成的待办不能修改内容' : '修改内容'}
                      onClick={() => startEdit(todo)}
                    >
                      编辑
                    </button>
                    <button
                      className="btn btn-danger btn-sm"
                      disabled={busy}
                      onClick={() => void handleDelete(todo)}
                    >
                      删除
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>

          {/* 分页。页码由 page 和 pages 决定。 */}
          <div className="pager">
            <button
              className="btn btn-ghost btn-sm"
              // 已经是第 1 页就不能再往前。
              disabled={page <= 1}
              // 用函数式更新，在当前页码上减 1，并且不会小于 1。
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              上一页
            </button>
            <span>
              {/* 没有数据时 pages 是 0，显示成“第 1 / 1 页”，避免出现“第 1 / 0 页”。 */}
              第 {page} / {Math.max(pages, 1)} 页
            </span>
            <button
              className="btn btn-ghost btn-sm"
              // 没有数据，或者已经是最后一页时，不能再往后。
              disabled={pages === 0 || page >= pages}
              onClick={() => setPage((p) => p + 1)}
            >
              下一页
            </button>
          </div>
        </section>

        {/* 右侧历史。数据是 logs，进入页面时拉一次，每次增删改后再拉一次。 */}
        <aside className="card side-card">
          <h2>历史记录</h2>
          <p className="hint">按时间倒序，最近 30 条操作</p>
          <ul className="log-list">
            {/* 一条流水都没有时的占位。 */}
            {logs.length === 0 && <li className="empty">暂无记录</li>}
            {logs.map((log) => (
              <li key={log.id}>
                {/* tag-create、tag-delete 等类名决定标签颜色。未知动作就显示原始英文。 */}
                <span className={`tag tag-${log.action}`}>{ACTION_TEXT[log.action] ?? log.action}</span>
                <div className="log-body">
                  {/* 后端写好的句子，例如“内容：买牛奶 -> 买面包”。 */}
                  <span className="log-detail">{log.detail}</span>
                  <span className="log-time">{fmt(log.created_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        </aside>
      </main>

      {/* toast 为 null 时这一行什么都不画。有内容时固定在页面底部。 */}
      {toast && <div className={`toast ${toast.type}`}>{toast.text}</div>}
    </div>
  )
}
