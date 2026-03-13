import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

const mockNavigate = vi.fn();
const mockToggleThreadSidebar = vi.fn();
const mockToggleDefinedTerms = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mockNavigate,
}));

vi.mock("@/stores/app-store", () => ({
  useAppStore: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({
        toggleThreadSidebar: mockToggleThreadSidebar,
        toggleDefinedTerms: mockToggleDefinedTerms,
      }),
    {
      getState: () => ({
        toggleThreadSidebar: mockToggleThreadSidebar,
        toggleDefinedTerms: mockToggleDefinedTerms,
      }),
    },
  ),
}));

import { useKeyboardShortcuts, useReviewShortcuts } from "@/hooks/use-keyboard-shortcuts";

function fireKeyDown(
  key: string,
  opts: Partial<KeyboardEventInit> = {},
  target?: HTMLElement,
) {
  const event = new KeyboardEvent("keydown", {
    key,
    bubbles: true,
    ...opts,
  });
  (target ?? document).dispatchEvent(event);
}

describe("useKeyboardShortcuts", () => {
  const onOpenCommandPalette = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function setup() {
    return renderHook(() =>
      useKeyboardShortcuts({ onOpenCommandPalette }),
    );
  }

  it("Cmd+K calls onOpenCommandPalette", () => {
    setup();
    fireKeyDown("k", { metaKey: true });
    expect(onOpenCommandPalette).toHaveBeenCalledTimes(1);
  });

  it("Ctrl+K calls onOpenCommandPalette", () => {
    setup();
    fireKeyDown("k", { ctrlKey: true });
    expect(onOpenCommandPalette).toHaveBeenCalledTimes(1);
  });

  it("Cmd+N navigates to /chat", () => {
    setup();
    fireKeyDown("n", { metaKey: true });
    expect(mockNavigate).toHaveBeenCalledWith({ to: "/chat" });
  });

  it("Ctrl+N navigates to /chat", () => {
    setup();
    fireKeyDown("n", { ctrlKey: true });
    expect(mockNavigate).toHaveBeenCalledWith({ to: "/chat" });
  });

  it("Cmd+B toggles thread sidebar", () => {
    setup();
    fireKeyDown("b", { metaKey: true });
    expect(mockToggleThreadSidebar).toHaveBeenCalledTimes(1);
  });

  it("Ctrl+B toggles thread sidebar", () => {
    setup();
    fireKeyDown("b", { ctrlKey: true });
    expect(mockToggleThreadSidebar).toHaveBeenCalledTimes(1);
  });

  it("Cmd+D toggles defined terms", () => {
    setup();
    fireKeyDown("d", { metaKey: true });
    expect(mockToggleDefinedTerms).toHaveBeenCalledTimes(1);
  });

  it("Ctrl+D toggles defined terms", () => {
    setup();
    fireKeyDown("d", { ctrlKey: true });
    expect(mockToggleDefinedTerms).toHaveBeenCalledTimes(1);
  });

  it("/ focuses search input when not in input/textarea", () => {
    const searchInput = document.createElement("input");
    searchInput.setAttribute("data-search-input", "");
    document.body.appendChild(searchInput);
    const focusSpy = vi.spyOn(searchInput, "focus");

    setup();
    fireKeyDown("/");
    expect(focusSpy).toHaveBeenCalledTimes(1);

    document.body.removeChild(searchInput);
  });

  it("/ does NOT trigger when focus is in an input", () => {
    const searchInput = document.createElement("input");
    searchInput.setAttribute("data-search-input", "");
    document.body.appendChild(searchInput);
    const focusSpy = vi.spyOn(searchInput, "focus");

    const activeInput = document.createElement("input");
    document.body.appendChild(activeInput);

    setup();
    // Dispatch from an input element
    fireKeyDown("/", {}, activeInput);
    expect(focusSpy).not.toHaveBeenCalled();

    document.body.removeChild(searchInput);
    document.body.removeChild(activeInput);
  });

  it("/ does NOT trigger when focus is in a textarea", () => {
    const searchInput = document.createElement("input");
    searchInput.setAttribute("data-search-input", "");
    document.body.appendChild(searchInput);
    const focusSpy = vi.spyOn(searchInput, "focus");

    const textarea = document.createElement("textarea");
    document.body.appendChild(textarea);

    setup();
    fireKeyDown("/", {}, textarea);
    expect(focusSpy).not.toHaveBeenCalled();

    document.body.removeChild(searchInput);
    document.body.removeChild(textarea);
  });

  it("cleans up event listener on unmount", () => {
    const removeEventListenerSpy = vi.spyOn(document, "removeEventListener");
    const { unmount } = setup();
    unmount();
    expect(removeEventListenerSpy).toHaveBeenCalledWith(
      "keydown",
      expect.any(Function),
    );
  });

  it("regular keys without modifiers do not trigger shortcuts", () => {
    setup();
    fireKeyDown("k");
    expect(onOpenCommandPalette).not.toHaveBeenCalled();
    fireKeyDown("n");
    expect(mockNavigate).not.toHaveBeenCalled();
    fireKeyDown("b");
    expect(mockToggleThreadSidebar).not.toHaveBeenCalled();
    fireKeyDown("d");
    expect(mockToggleDefinedTerms).not.toHaveBeenCalled();
  });

  it("Shift+? toggles shortcutsHelpOpen state", () => {
    const { result } = setup();
    expect(result.current.shortcutsHelpOpen).toBe(false);

    act(() => {
      fireKeyDown("?", { shiftKey: true });
    });
    expect(result.current.shortcutsHelpOpen).toBe(true);

    act(() => {
      fireKeyDown("?", { shiftKey: true });
    });
    expect(result.current.shortcutsHelpOpen).toBe(false);
  });

  it("setShortcutsHelpOpen can close the dialog", () => {
    const { result } = setup();

    act(() => {
      result.current.setShortcutsHelpOpen(true);
    });
    expect(result.current.shortcutsHelpOpen).toBe(true);

    act(() => {
      result.current.setShortcutsHelpOpen(false);
    });
    expect(result.current.shortcutsHelpOpen).toBe(false);
  });
});

describe("useReviewShortcuts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("j moves focus down", () => {
    const onFocusChange = vi.fn();
    renderHook(() =>
      useReviewShortcuts({
        itemCount: 5,
        focusedIndex: 1,
        onFocusChange,
      }),
    );

    fireKeyDown("j");
    expect(onFocusChange).toHaveBeenCalledWith(2);
  });

  it("j does not exceed itemCount - 1", () => {
    const onFocusChange = vi.fn();
    renderHook(() =>
      useReviewShortcuts({
        itemCount: 3,
        focusedIndex: 2,
        onFocusChange,
      }),
    );

    fireKeyDown("j");
    expect(onFocusChange).toHaveBeenCalledWith(2);
  });

  it("k moves focus up", () => {
    const onFocusChange = vi.fn();
    renderHook(() =>
      useReviewShortcuts({
        itemCount: 5,
        focusedIndex: 3,
        onFocusChange,
      }),
    );

    fireKeyDown("k");
    expect(onFocusChange).toHaveBeenCalledWith(2);
  });

  it("k does not go below 0", () => {
    const onFocusChange = vi.fn();
    renderHook(() =>
      useReviewShortcuts({
        itemCount: 5,
        focusedIndex: 0,
        onFocusChange,
      }),
    );

    fireKeyDown("k");
    expect(onFocusChange).toHaveBeenCalledWith(0);
  });

  it("k with meta key is ignored (allows Cmd+K to pass through)", () => {
    const onFocusChange = vi.fn();
    renderHook(() =>
      useReviewShortcuts({
        itemCount: 5,
        focusedIndex: 3,
        onFocusChange,
      }),
    );

    fireKeyDown("k", { metaKey: true });
    expect(onFocusChange).not.toHaveBeenCalled();
  });

  it("Enter calls onOpen with focused index", () => {
    const onOpen = vi.fn();
    renderHook(() =>
      useReviewShortcuts({
        itemCount: 5,
        focusedIndex: 2,
        onFocusChange: vi.fn(),
        onOpen,
      }),
    );

    fireKeyDown("Enter");
    expect(onOpen).toHaveBeenCalledWith(2);
  });

  it("Enter does not call onOpen when no item is focused", () => {
    const onOpen = vi.fn();
    renderHook(() =>
      useReviewShortcuts({
        itemCount: 5,
        focusedIndex: -1,
        onFocusChange: vi.fn(),
        onOpen,
      }),
    );

    fireKeyDown("Enter");
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("Escape calls onEscape", () => {
    const onEscape = vi.fn();
    renderHook(() =>
      useReviewShortcuts({
        itemCount: 5,
        focusedIndex: 0,
        onFocusChange: vi.fn(),
        onEscape,
      }),
    );

    fireKeyDown("Escape");
    expect(onEscape).toHaveBeenCalledTimes(1);
  });

  it("r calls onToggleRelevance with focused index", () => {
    const onToggleRelevance = vi.fn();
    renderHook(() =>
      useReviewShortcuts({
        itemCount: 5,
        focusedIndex: 1,
        onFocusChange: vi.fn(),
        onToggleRelevance,
      }),
    );

    fireKeyDown("r");
    expect(onToggleRelevance).toHaveBeenCalledWith(1);
  });

  it("p calls onTogglePrivilege with focused index", () => {
    const onTogglePrivilege = vi.fn();
    renderHook(() =>
      useReviewShortcuts({
        itemCount: 5,
        focusedIndex: 1,
        onFocusChange: vi.fn(),
        onTogglePrivilege,
      }),
    );

    fireKeyDown("p");
    expect(onTogglePrivilege).toHaveBeenCalledWith(1);
  });

  it("[ calls onPrevDocument", () => {
    const onPrevDocument = vi.fn();
    renderHook(() =>
      useReviewShortcuts({
        itemCount: 5,
        focusedIndex: 0,
        onFocusChange: vi.fn(),
        onPrevDocument,
      }),
    );

    fireKeyDown("[");
    expect(onPrevDocument).toHaveBeenCalledTimes(1);
  });

  it("] calls onNextDocument", () => {
    const onNextDocument = vi.fn();
    renderHook(() =>
      useReviewShortcuts({
        itemCount: 5,
        focusedIndex: 0,
        onFocusChange: vi.fn(),
        onNextDocument,
      }),
    );

    fireKeyDown("]");
    expect(onNextDocument).toHaveBeenCalledTimes(1);
  });

  it("shortcuts are ignored when focus is in an input", () => {
    const onFocusChange = vi.fn();
    const onOpen = vi.fn();
    renderHook(() =>
      useReviewShortcuts({
        itemCount: 5,
        focusedIndex: 0,
        onFocusChange,
        onOpen,
      }),
    );

    const input = document.createElement("input");
    document.body.appendChild(input);

    fireKeyDown("j", {}, input);
    expect(onFocusChange).not.toHaveBeenCalled();

    fireKeyDown("Enter", {}, input);
    expect(onOpen).not.toHaveBeenCalled();

    document.body.removeChild(input);
  });

  it("cleans up event listener on unmount", () => {
    const removeEventListenerSpy = vi.spyOn(document, "removeEventListener");
    const { unmount } = renderHook(() =>
      useReviewShortcuts({
        itemCount: 5,
        focusedIndex: 0,
        onFocusChange: vi.fn(),
      }),
    );
    unmount();
    expect(removeEventListenerSpy).toHaveBeenCalledWith(
      "keydown",
      expect.any(Function),
    );
  });
});
