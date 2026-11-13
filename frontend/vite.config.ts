import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 关键点：
// 1. base: './'   —— 产物引用资源用相对路径，放到任意子路径下都能跑
// 2. outDir: '../backend/dist' —— 打包直接输出到后端 dist 目录
// 3. build.assetsDir: 'static' —— 静态资源统一进 static/，最终得到 index.html + static/
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: '../backend/dist',
    assetsDir: 'static',
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      // 开发时前端调 /api/xxx，自动转发到本地后端，避免跨域
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
