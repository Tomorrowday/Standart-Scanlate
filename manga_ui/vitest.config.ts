// manga_ui/vitest.config.ts
// Конфигурация быстрых unit-тестов фронтенда (Vitest, node-окружение).

import path from "node:path"
import { defineConfig } from "vitest/config"

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "node",
    include: ["__tests__/**/*.test.ts"],
  },
})
