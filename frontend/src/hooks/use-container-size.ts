import { useRef, useState, useEffect, useCallback, type RefObject } from "react";

interface ContainerSize {
  ref: RefObject<HTMLDivElement | null>;
  width: number;
  height: number;
}

export function useContainerSize(debounceMs: number = 100): ContainerSize {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  const updateSize = useCallback(
    (entries: ResizeObserverEntry[]) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      setSize((prev) =>
        prev.width === Math.round(width) && prev.height === Math.round(height)
          ? prev
          : { width: Math.round(width), height: Math.round(height) },
      );
    },
    [],
  );

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const observer = new ResizeObserver((entries) => {
      if (timeoutId) clearTimeout(timeoutId);
      timeoutId = setTimeout(() => updateSize(entries), debounceMs);
    });

    observer.observe(el);

    const { width, height } = el.getBoundingClientRect();
    setSize({ width: Math.round(width), height: Math.round(height) });

    return () => {
      observer.disconnect();
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [debounceMs, updateSize]);

  return { ref, width: size.width, height: size.height };
}
