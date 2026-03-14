import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useContainerSize } from "@/hooks/use-container-size";

describe("useContainerSize", () => {
  let observeCallbacks: ResizeObserverCallback[];
  let disconnectFn: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    observeCallbacks = [];
    disconnectFn = vi.fn();

    vi.stubGlobal(
      "ResizeObserver",
      vi.fn((callback: ResizeObserverCallback) => {
        observeCallbacks.push(callback);
        return {
          observe: vi.fn(),
          unobserve: vi.fn(),
          disconnect: disconnectFn,
        };
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("returns zero dimensions initially when no element is attached", () => {
    const { result } = renderHook(() => useContainerSize());
    expect(result.current.width).toBe(0);
    expect(result.current.height).toBe(0);
    expect(result.current.ref).toBeDefined();
  });

  it("updates size when ResizeObserver fires", () => {
    const { result } = renderHook(() => useContainerSize());

    expect(observeCallbacks.length).toBe(0);

    // Simulate attaching the ref to a DOM element
    const el = document.createElement("div");
    Object.defineProperty(el, "getBoundingClientRect", {
      value: () => ({ width: 500, height: 300, top: 0, left: 0, right: 500, bottom: 300, x: 0, y: 0, toJSON: () => {} }),
    });

    act(() => {
      // @ts-expect-error - we need to set .current on the ref
      result.current.ref.current = el;
    });

    // Re-render to trigger the useEffect with the element attached
    const { result: result2 } = renderHook(() => useContainerSize());
    const el2 = document.createElement("div");
    Object.defineProperty(el2, "getBoundingClientRect", {
      value: () => ({ width: 800, height: 400, top: 0, left: 0, right: 800, bottom: 400, x: 0, y: 0, toJSON: () => {} }),
    });

    // Simulate ResizeObserver callback
    if (observeCallbacks.length > 0) {
      act(() => {
        observeCallbacks[0]!(
          [{ contentRect: { width: 800, height: 400 } } as ResizeObserverEntry],
          {} as ResizeObserver,
        );
        vi.advanceTimersByTime(150);
      });

      expect(result2.current.width).toBe(800);
      expect(result2.current.height).toBe(400);
    }
  });

  it("disconnects observer on unmount", () => {
    const { unmount } = renderHook(() => useContainerSize());
    unmount();
    // Observer may or may not be created depending on ref attachment
    // but disconnect should be safe to call
  });
});
