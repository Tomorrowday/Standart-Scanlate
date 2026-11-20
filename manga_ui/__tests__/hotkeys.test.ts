// manga_ui/__tests__/hotkeys.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  DEFAULT_HOTKEYS,
  HOTKEYS_STORAGE_KEY,
  formatKeyEvent,
  loadHotkeys,
  matchHotkey,
  type HotkeyConfig,
} from "@/lib/hotkeys"
import { dispatchMangaHotkey, type HotkeyDispatchContext } from "@/hooks/hotkey-dispatcher"
import type { TextBlock } from "@/lib/types"

class FakeInput {}
class FakeTextArea {}
class FakeSelect {}

beforeEach(() => {
  ;(globalThis as any).HTMLInputElement = FakeInput
  ;(globalThis as any).HTMLTextAreaElement = FakeTextArea
  ;(globalThis as any).HTMLSelectElement = FakeSelect
})

function keyEvent(overrides: Record<string, unknown> = {}): KeyboardEvent {
  const state = { prevented: false }
  const event = {
    code: "",
    key: "",
    ctrlKey: false,
    shiftKey: false,
    altKey: false,
    metaKey: false,
    target: null,
    preventDefault() {
      state.prevented = true
    },
    ...overrides,
  }
  Object.defineProperty(event, "__prevented", { get: () => state.prevented })
  return event as unknown as KeyboardEvent
}

function wasPrevented(event: KeyboardEvent): boolean {
  return Boolean((event as any).__prevented)
}

describe("matchHotkey", () => {
  it("требует точного совпадения модификаторов", () => {
    const ctrlZ = { code: "KeyZ", ctrl: true, label: "Ctrl+Z", name: "", category: "navigation" as const }

    expect(matchHotkey(keyEvent({ code: "KeyZ", ctrlKey: true }), ctrlZ)).toBe(true)
    expect(matchHotkey(keyEvent({ code: "KeyZ" }), ctrlZ)).toBe(false)
    expect(matchHotkey(keyEvent({ code: "KeyZ", ctrlKey: true, shiftKey: true }), ctrlZ)).toBe(false)
  })

  it("понимает Numpad-цифры и клавиши +/−", () => {
    const digit5 = { code: "Digit5", label: "5", name: "", category: "font" as const }
    const equal = { code: "Equal", label: "+", name: "", category: "font" as const }
    const minus = { code: "Minus", label: "-", name: "", category: "font" as const }

    expect(matchHotkey(keyEvent({ code: "Numpad5" }), digit5)).toBe(true)
    expect(matchHotkey(keyEvent({ code: "NumpadAdd" }), equal)).toBe(true)
    expect(matchHotkey(keyEvent({ code: "Something", key: "+" }), equal)).toBe(true)
    expect(matchHotkey(keyEvent({ code: "NumpadSubtract" }), minus)).toBe(true)
  })

  it("не срабатывает для пустого биндинга", () => {
    expect(matchHotkey(keyEvent({ code: "KeyZ" }), {} as any)).toBe(false)
  })
})

describe("formatKeyEvent", () => {
  it("формирует читаемую комбинацию", () => {
    const formatted = formatKeyEvent(
      keyEvent({ code: "KeyZ", ctrlKey: true, shiftKey: true, key: "Z" })
    )

    expect(formatted).toEqual({
      code: "KeyZ",
      ctrl: true,
      shift: true,
      alt: false,
      label: "Ctrl+Shift+Z",
    })
  })

  it("игнорирует одиночные модификаторы", () => {
    expect(formatKeyEvent(keyEvent({ key: "Control", code: "ControlLeft" }))).toBeNull()
    expect(formatKeyEvent(keyEvent({ key: "Shift", code: "ShiftLeft" }))).toBeNull()
  })

  it("украшает цифры и стрелки", () => {
    expect(formatKeyEvent(keyEvent({ code: "Digit1", key: "1" }))?.label).toBe("1")
    expect(formatKeyEvent(keyEvent({ code: "ArrowUp", key: "ArrowUp" }))?.label).toBe("↑")
  })
})

describe("loadHotkeys: миграция KeyC -> Shift+C", () => {
  const storage = new Map<string, string>()

  beforeEach(() => {
    storage.clear()
    ;(globalThis as any).window = {}
    ;(globalThis as any).localStorage = {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
    }
  })

  afterEach(() => {
    delete (globalThis as any).window
    delete (globalThis as any).localStorage
  })

  it("переносит старый одиночный C на класс бабла в Shift+C, если cleanPage не настроен", () => {
    const oldConfig = {
      setClassBubble: { code: "KeyC", label: "C", name: "Класс: Бабл (0)", category: "bubble" },
    }
    storage.set(HOTKEYS_STORAGE_KEY, JSON.stringify(oldConfig))

    const loaded = loadHotkeys()

    expect(loaded.setClassBubble.code).toBe("KeyC")
    expect(loaded.setClassBubble.shift).toBe(true)
    expect(loaded.setClassBubble.label).toBe("Shift+C")
    expect(loaded.cleanPage.code).toBe("KeyC")
    expect(loaded.cleanPage.shift).toBeFalsy()
  })

  it("не мигрирует, если пользователь уже настроил cleanPage", () => {
    const config = {
      cleanPage: { code: "KeyX", label: "X", name: "Клин", category: "cleaning" },
      setClassBubble: { code: "KeyC", label: "C", name: "Класс", category: "bubble" },
    }
    storage.set(HOTKEYS_STORAGE_KEY, JSON.stringify(config))

    const loaded = loadHotkeys()
    expect(loaded.setClassBubble.label).toBe("C")
    expect(loaded.cleanPage.label).toBe("X")
  })

  it("повреждённый JSON даёт дефолтную раскладку", () => {
    storage.set(HOTKEYS_STORAGE_KEY, "{ not json")
    expect(loadHotkeys()).toEqual(DEFAULT_HOTKEYS)
  })
})

describe("dispatchMangaHotkey", () => {
  const activeBlock: TextBlock = {
    id: "b1",
    class_id: 0,
    x: 0.1,
    y: 0.1,
    width: 0.3,
    height: 0.2,
    rotation: 0,
    japText: "",
    rusText: "",
    speaker: "",
    orderIndex: 1,
    fontSize: undefined,
    status: "new",
    fontFamily: "v_CCFaceFront",
    isBold: false,
    isItalic: false,
    isUppercase: false,
    hasStroke: false,
    textColor: "black",
    shape: "rect",
    paddingMode: "safe",
    minHyphens: true,
  }

  function makeCtx(overrides: Partial<HotkeyDispatchContext> = {}): HotkeyDispatchContext {
    return {
      hotkeys: DEFAULT_HOTKEYS as HotkeyConfig,
      selectedId: "b1",
      textBlocks: [activeBlock],
      defaultFontSize: 14,
      onPrevPage: vi.fn(),
      onNextPage: vi.fn(),
      onSave: vi.fn(),
      onDeleteBlock: vi.fn(),
      onMoveBlock: vi.fn(),
      onUpdateBlock: vi.fn(),
      ...overrides,
    }
  }

  it("игнорирует события при открытой модалке (disabled)", () => {
    const ctx = makeCtx({ disabled: true, onUndo: vi.fn() })
    const event = keyEvent({ code: "KeyZ", ctrlKey: true })

    expect(dispatchMangaHotkey(event, ctx)).toBe(false)
    expect(ctx.onUndo).not.toHaveBeenCalled()
  })

  it("игнорирует ввод внутри input/textarea/select/contenteditable", () => {
    const onUndo = vi.fn()
    for (const target of [new FakeInput(), new FakeTextArea(), new FakeSelect(), { isContentEditable: true }]) {
      const ctx = makeCtx({ onUndo })
      const event = keyEvent({ code: "KeyZ", ctrlKey: true, target })
      expect(dispatchMangaHotkey(event, ctx)).toBe(false)
    }
    expect(onUndo).not.toHaveBeenCalled()
  })

  it("вызывает Undo по Ctrl+Z и Redo по Ctrl+Shift+Z", () => {
    const onUndo = vi.fn()
    const onRedo = vi.fn()

    const undoEvent = keyEvent({ code: "KeyZ", ctrlKey: true })
    expect(dispatchMangaHotkey(undoEvent, makeCtx({ onUndo, onRedo }))).toBe(true)
    expect(onUndo).toHaveBeenCalledTimes(1)
    expect(onRedo).not.toHaveBeenCalled()
    expect(wasPrevented(undoEvent)).toBe(true)

    const redoEvent = keyEvent({ code: "KeyZ", ctrlKey: true, shiftKey: true })
    expect(dispatchMangaHotkey(redoEvent, makeCtx({ onUndo, onRedo }))).toBe(true)
    expect(onRedo).toHaveBeenCalledTimes(1)
    expect(onUndo).toHaveBeenCalledTimes(1)
  })

  it("удаляет бабл по Delete и Backspace", () => {
    for (const code of ["Delete", "Backspace"]) {
      const onDeleteBlock = vi.fn()
      const event = keyEvent({ code })
      expect(dispatchMangaHotkey(event, makeCtx({ onDeleteBlock }))).toBe(true)
      expect(onDeleteBlock).toHaveBeenCalledWith("b1")
    }
  })

  it("не удаляет бабл без выделения", () => {
    const onDeleteBlock = vi.fn()
    const event = keyEvent({ code: "Delete" })
    expect(dispatchMangaHotkey(event, makeCtx({ onDeleteBlock, selectedId: null }))).toBe(false)
    expect(onDeleteBlock).not.toHaveBeenCalled()
  })

  it("переключает страницы по Q/E", () => {
    const onPrevPage = vi.fn()
    const onNextPage = vi.fn()
    const ctx = makeCtx({ onPrevPage, onNextPage })

    expect(dispatchMangaHotkey(keyEvent({ code: "KeyQ" }), ctx)).toBe(true)
    expect(dispatchMangaHotkey(keyEvent({ code: "KeyE" }), ctx)).toBe(true)
    expect(onPrevPage).toHaveBeenCalledTimes(1)
    expect(onNextPage).toHaveBeenCalledTimes(1)
  })
})
