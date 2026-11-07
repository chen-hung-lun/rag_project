import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vue()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    // 前端呼叫 /api 時轉給 FastAPI，兩邊同源就不需要設定 CORS
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
