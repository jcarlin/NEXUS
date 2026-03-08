import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";

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

import { useKeyboardShortcuts } from "@/hooks/use-keyboard-shortcuts";

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
});
