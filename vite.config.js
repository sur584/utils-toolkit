import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';
import { copyFileSync, existsSync, mkdirSync, readdirSync, rmSync, readFileSync, writeFileSync } from 'fs';

const tools = ['image-tool', 'bg-remover', 'image-composite', 'text-remover', 'watermark-tool'];

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'copy-to-tools',
      closeBundle() {
        // 1. 复制 index.html 到各工具目录，同时移除 crossorigin 属性
        for (const tool of tools) {
          const src = resolve(__dirname, `dist/src/${tool}/index.html`);
          const dest = resolve(__dirname, `tools/${tool}/index.html`);
          if (existsSync(src)) {
            let html = readFileSync(src, 'utf-8');
            html = html.replace(/ crossorigin(?=[ >])/g, '');
            writeFileSync(dest, html);
          }
        }

        // 2. 同步 dist/assets 到根目录 assets（后端从这里提供静态文件）
        const distAssets = resolve(__dirname, 'dist/assets');
        const rootAssets = resolve(__dirname, 'assets');
        if (existsSync(distAssets)) {
          // 清空旧 assets
          if (existsSync(rootAssets)) {
            rmSync(rootAssets, { recursive: true });
          }
          mkdirSync(rootAssets, { recursive: true });
          for (const file of readdirSync(distAssets)) {
            copyFileSync(resolve(distAssets, file), resolve(rootAssets, file));
          }
        }
      }
    }
  ],
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: Object.fromEntries(
        tools.map(tool => [tool, resolve(__dirname, `src/${tool}/index.html`)])
      )
    }
  }
});
