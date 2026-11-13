// 入口文件。index.html 里的 <script type="module" src="/src/main.tsx"> 会加载这里。
// 这个文件不做业务，只负责把 App 组件画到页面上，并带上全局样式。

// StrictMode 是 React 的开发辅助组件。开发时它会故意把部分渲染多跑一遍，用来暴露不干净的副作用。
// 生产打包后这层检查不会改变页面功能。
import { StrictMode } from 'react'
// createRoot 是 React 18 的挂载方法。它接管某一个真实 DOM 节点，之后的更新都由 React 负责。
import { createRoot } from 'react-dom/client'
// 整页待办界面都在 App.tsx 里。这里只把它引进来。
import App from './App'
// 引入样式文件。Vite 看到这行就会把 styles.css 应用到整个页面。
import './styles.css'

// document.getElementById('root') 找到 index.html 里的 <div id="root">。
// 末尾的 ! 告诉 TypeScript：这个节点一定存在，不用再做空值检查。
// render 的参数就是要画出来的组件树。
createRoot(document.getElementById('root')!).render(
  // StrictMode 包在最外层。它本身不产生可见的 DOM。
  <StrictMode>
    {/* App 是页面上唯一的业务组件。列表、搜索、历史记录都从这里开始。 */}
    <App />
  </StrictMode>,
)
