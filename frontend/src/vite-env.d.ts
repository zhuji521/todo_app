/// <reference types="vite/client" />

// 这是给 TypeScript 看的类型声明，不会生成任何运行代码。
// 上面那行把 Vite 自己的类型引进来，这样 import.meta.env 才有类型。

// ImportMetaEnv 描述“构建时能读到哪些以 VITE_ 开头的环境变量”。
interface ImportMetaEnv {
  // 可选的接口前缀。api.ts 用它拼请求地址。
  // 不配置时是 undefined，api.ts 会退回空字符串，请求就发到当前网站的 /api/...。
  readonly VITE_API_BASE?: string
}

// 把上面的环境变量挂到 import.meta.env 上。
// 没有这个声明时，api.ts 里的 import.meta.env.VITE_API_BASE 会报类型错误。
interface ImportMeta {
  // env 只读，代码里不能给它重新赋值。
  readonly env: ImportMetaEnv
}
