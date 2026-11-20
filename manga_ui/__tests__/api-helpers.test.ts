// manga_ui/__tests__/api-helpers.test.ts
import { describe, expect, it } from "vitest"

import { pickBestOllamaModel } from "@/lib/api/ollama"
import { toPageBlocksPayload } from "@/lib/api/pages"
import type { TextBlock } from "@/lib/types"

function textBlock(overrides: Partial<TextBlock> = {}): TextBlock {
  return {
    id: "b1",
    class_id: 0,
    x: 0.1,
    y: 0.2,
    width: 0.3,
    height: 0.4,
    rotation: 0,
    japText: "こんにちは",
    rusText: "Привет",
    speaker: "Макима",
    orderIndex: 1,
    status: "translated",
    fontFamily: "v_CCFaceFront",
    isBold: false,
    isItalic: false,
    isUppercase: false,
    hasStroke: false,
    textColor: "black",
    shape: "rect",
    paddingMode: "safe",
    minHyphens: true,
    ...overrides,
  }
}

describe("toPageBlocksPayload", () => {
  it("преобразует TextBlock в snake_case payload", () => {
    const [payload] = toPageBlocksPayload([textBlock()])

    expect(payload).toMatchObject({
      id: "b1",
      class_id: 0,
      x: 0.1,
      y: 0.2,
      width: 0.3,
      height: 0.4,
      jap_text: "こんにちは",
      rus_text: "Привет",
      speaker: "Макима",
      order_index: 1,
      font_family: "v_CCFaceFront",
      status: "translated",
    })
  })

  it("не отправляет font_size для Auto (undefined)", () => {
    const [payload] = toPageBlocksPayload([textBlock({ fontSize: undefined })])
    expect(payload.font_size).toBeUndefined()

    const [explicit] = toPageBlocksPayload([textBlock({ fontSize: 18 })])
    expect(explicit.font_size).toBe(18)
  })

  it("нормализует булевы поля и дефолты", () => {
    const [payload] = toPageBlocksPayload([
      textBlock({
        class_id: undefined as unknown as number,
        speaker: undefined as unknown as string,
        orderIndex: 0,
        fontFamily: undefined as unknown as string,
        isBold: undefined as unknown as boolean,
        textColor: undefined as unknown as "black",
        shape: undefined as unknown as "rect",
        paddingMode: undefined as unknown as "safe",
        minHyphens: undefined as unknown as boolean,
      }),
    ])

    expect(payload.class_id).toBe(0)
    expect(payload.speaker).toBe("")
    expect(payload.order_index).toBe(0)
    expect(payload.font_family).toBe("v_CCFaceFront")
    expect(payload.is_bold).toBe(false)
    expect(payload.text_color).toBe("black")
    expect(payload.shape).toBe("rect")
    expect(payload.padding_mode).toBe("safe")
    expect(payload.min_hyphens).toBe(true)
  })
})

describe("pickBestOllamaModel", () => {
  it("возвращает qwen по умолчанию для пустого списка", () => {
    expect(pickBestOllamaModel([])).toBe("qwen2.5:7b")
  })

  it("игнорирует embedding-модели", () => {
    expect(
      pickBestOllamaModel(["nomic-embed-text:latest", "bge-m3", "llama3.1:8b"])
    ).toBe("llama3.1:8b")
    expect(pickBestOllamaModel(["mxbai-embed-large", "qwen2.5:7b"])).toBe("qwen2.5:7b")
  })

  it("предпочитает чат-модели с известным именем и берёт первую подходящую", () => {
    expect(pickBestOllamaModel(["phi3:mini", "mistral:7b", "qwen2.5:7b"])).toBe("mistral:7b")
    expect(pickBestOllamaModel(["phi3:mini", "qwen2.5:7b"])).toBe("qwen2.5:7b")
    expect(pickBestOllamaModel(["phi3:mini", "gemma:2b"])).toBe("gemma:2b")
  })

  it("иначе берёт первую доступную модель", () => {
    expect(pickBestOllamaModel(["phi3:mini", "wizardlm:7b"])).toBe("phi3:mini")
  })
})
