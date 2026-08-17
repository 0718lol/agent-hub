import React from "react"
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react"

// Mock CSS modules
vi.mock("./SettingsPanel.module.css", () => ({
  default: {
    overlay: "overlay",
    modal: "modal",
    header: "header",
    closeBtn: "closeBtn",
    generalSection: "generalSection",
    row: "row",
    tabBar: "tabBar",
    tabBtnActive: "tabBtnActive",
    tabBtnInactive: "tabBtnInactive",
    statusBanner: "statusBanner",
    statusText: "statusText",
    label: "label",
    inputSecondary: "inputSecondary",
    saveBtn: "saveBtn",
    presetsContainer: "presetsContainer",
    presetGroup: "presetGroup",
    presetBtn: "presetBtn",
    providerGroup: "providerGroup",
    optionBtnActive: "optionBtnActive",
    optionBtnInactive: "optionBtnInactive",
    sliderRow: "sliderRow",
    sliderCol: "sliderCol",
    sliderLabels: "sliderLabels",
    disconnectBtn: "disconnectBtn",
    switchBtn: "switchBtn",
    statusActions: "statusActions",
    warningInline: "warningInline",
    ollamaRefreshBtn: "ollamaRefreshBtn",
  },
}))

// Mock child tab components to keep tests focused on SettingsPanel logic
vi.mock("./LLMTab", () => ({
  default: function MockLLMTab(props) {
    return (
      <div data-testid="llm-tab">
        <span>LLM Tab Mock</span>
        <span>Provider: {props.provider}</span>
        <span>Model: {props.model}</span>
        {props.configured && <span>Configured</span>}
        {props.configured && <button onClick={props.handleDisconnect}>Disconnect</button>}
      </div>
    )
  },
}))

vi.mock("./QualityGateTab", () => ({
  default: function MockQualityGateTab() {
    return <div data-testid="quality-tab">Quality Gate Tab Mock</div>
  },
}))

vi.mock("./PromptLayersTab", () => ({
  default: function MockPromptLayersTab() {
    return <div data-testid="prompt-tab">Prompt Layers Tab Mock</div>
  },
}))

vi.mock("./CronTasksTab", () => ({
  default: function MockCronTasksTab() {
    return <div data-testid="cron-tab">Cron Tasks Tab Mock</div>
  },
}))

vi.mock("./OtherTab", () => ({
  default: function MockOtherTab(props) {
    return <div data-testid="other-tab"><button onClick={() => props.handleKbDelete("doc-1")}>Delete document</button></div>
  },
}))

vi.mock("./AdaptersTab", () => ({
  default: function MockAdaptersTab() {
    return <div data-testid="adapters-tab">Adapters Tab Mock</div>
  },
}))

vi.mock("./SecurityTab", () => ({
  default: function MockSecurityTab() {
    return <div data-testid="security-tab">Security Tab Mock</div>
  },
}))

vi.mock("./ToggleSwitch", () => ({
  default: function MockToggleSwitch({ checked, onChange }) {
    return <button data-testid="toggle-switch" onClick={onChange}>{checked ? "on" : "off"}</button>
  },
}))

// Mock stores
vi.mock("../../stores/themeStore", () => ({
  useThemeStore: vi.fn((selector) => {
    const state = { theme: "light", toggleTheme: vi.fn() }
    return selector(state)
  }),
}))

vi.mock("../../stores/chatStore", () => ({
  useChatStore: vi.fn((selector) => {
    const state = {
      activeConversationId: "conv_001",
      clearMessages: vi.fn(),
    }
    return selector(state)
  }),
}))

// Import after mocks are set up
import SettingsPanel from "./SettingsPanel"

describe("SettingsPanel", () => {
  let mockOnClose

  beforeEach(() => {
    mockOnClose = vi.fn()

    // Mock fetch globally
    global.fetch = vi.fn((url) => {
      if (url === "/api/settings/llm") {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              provider: "openai",
              base_url: "",
              model: "",
              temperature: 0.5,
              max_tokens: 8192,
              configured: false,
            }),
        })
      }
      if (url === "/api/settings/quality") {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              enabled: true,
              best_of_n: 1,
              max_retries: 1,
              use_llm_judge: false,
            }),
        })
      }
      if (url === "/api/prompt/layers") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([]),
        })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ status: "ok" }),
      })
    })

    // Mock window.confirm using spyOn instead of stubGlobal
    vi.spyOn(window, "confirm").mockReturnValue(true)

    // Mock localStorage
    Storage.prototype.getItem = vi.fn(() => null)
    Storage.prototype.setItem = vi.fn()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it("renders without crashing", () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    expect(screen.getByText("设置")).toBeInTheDocument()
  })

  it("displays LLM tab by default", () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    expect(screen.getByTestId("llm-tab")).toBeInTheDocument()
  })

  it("renders all tab buttons", () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    expect(screen.getByText("LLM 模型")).toBeInTheDocument()
    expect(screen.getByText("质量门")).toBeInTheDocument()
    expect(screen.getByText("Prompt 分层")).toBeInTheDocument()
    expect(screen.getByText("其他")).toBeInTheDocument()
    expect(screen.getByText("📅 自治")).toBeInTheDocument()
    expect(screen.getByText("外部 Agent")).toBeInTheDocument()
    expect(screen.getByText("🔒 安全")).toBeInTheDocument()
  })

  it("calls onClose when close button is clicked", () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    const closeBtn = screen.getByText("×")
    fireEvent.click(closeBtn)
    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it("calls onClose when overlay is clicked", () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    const overlay = document.querySelector("[class*=overlay]") || document.querySelector("[class*=Overlay]")
    if (overlay) {
      fireEvent.click(overlay)
      expect(mockOnClose).toHaveBeenCalledTimes(1)
    }
  })

  it("does not call onClose when modal content is clicked", () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    const modal = document.querySelector("[class*=modal]") || document.querySelector("[class*=Modal]")
    if (modal) {
      fireEvent.click(modal)
      expect(mockOnClose).not.toHaveBeenCalled()
    }
  })

  it("switches to quality tab when clicked", () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    expect(screen.getByTestId("llm-tab")).toBeInTheDocument()

    fireEvent.click(screen.getByText("质量门"))

    expect(screen.getByTestId("quality-tab")).toBeInTheDocument()
    expect(screen.queryByTestId("llm-tab")).not.toBeInTheDocument()
  })

  it("switches to prompt tab when clicked", () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    fireEvent.click(screen.getByText("Prompt 分层"))
    expect(screen.getByTestId("prompt-tab")).toBeInTheDocument()
  })

  it("switches to tools tab when clicked", () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    fireEvent.click(screen.getByText("其他"))
    expect(screen.getByTestId("other-tab")).toBeInTheDocument()
  })

  it("switches to cron tab when clicked", () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    fireEvent.click(screen.getByText("📅 自治"))
    expect(screen.getByTestId("cron-tab")).toBeInTheDocument()
  })

  it("switches to knowledge tab when clicked", () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    fireEvent.click(screen.getByText("外部 Agent"))
    expect(screen.getByTestId("adapters-tab")).toBeInTheDocument()
  })

  it("switches to security tab when clicked", () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    fireEvent.click(screen.getByText("🔒 安全"))
    expect(screen.getByTestId("security-tab")).toBeInTheDocument()
  })

  it("renders theme toggle", () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    expect(screen.getByText("界面主题")).toBeInTheDocument()
    expect(screen.getByTestId("toggle-switch")).toBeInTheDocument()
  })

  it("renders clear history button", () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    expect(screen.getByText("清空当前会话历史")).toBeInTheDocument()
    expect(screen.getByText("清空")).toBeInTheDocument()
  })

  it("fetches LLM settings on mount", async () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith("/api/settings/llm")
    })
  })

  it("fetches quality settings on mount", async () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith("/api/settings/quality")
    })
  })

  it("fetches prompt layers on mount", async () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith("/api/prompt/layers")
    })
  })

  it("disconnects LLM with DELETE", async () => {
    global.fetch = vi.fn((url, options) => {
      if (url === "/api/settings/llm" && options?.method === "DELETE") {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ configured: false, inherited: false }) })
      }
      if (url === "/api/settings/llm") {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ configured: true, provider: "openai", model: "gpt-test" }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: "ok" }) })
    })
    render(<SettingsPanel onClose={mockOnClose} />)
    await waitFor(() => expect(screen.getByText("Disconnect")).toBeInTheDocument())
    fireEvent.click(screen.getByText("Disconnect"))
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith("/api/settings/llm", { method: "DELETE" }))
  })

  it("deletes a default knowledge document with the file endpoint", async () => {
    render(<SettingsPanel onClose={mockOnClose} />)
    fireEvent.click(screen.getByText("其他"))
    fireEvent.click(screen.getByText("Delete document"))
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
      "/api/knowledge/__default__/files/doc-1",
      { method: "DELETE" },
    ))
  })
})
