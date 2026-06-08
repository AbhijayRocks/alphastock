import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// Dev-server port is environment-driven: set VITE_PORT (or PORT) in a .env
// file or the shell. Falls back to 4000 so it works with zero config.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const port = Number(env.VITE_PORT || env.PORT) || 4000

  return {
    plugins: [react()],
    resolve: {
      // shadcn-style "@/..." imports resolve to /src
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    clearScreen: false,
    server: {
      port,
      strictPort: true,
    },
    preview: {
      port,
      strictPort: true,
    },
  }
})
