import { useCallback } from "react";
import { toast } from "sonner";

export function useNotifications() {
  const success = useCallback((message: string) => {
    toast.success(message);
  }, []);

  const error = useCallback((message: string) => {
    toast.error(message);
  }, []);

  const info = useCallback((message: string) => {
    toast.info(message);
  }, []);

  const promise = useCallback(
    <T,>(
      fn: Promise<T>,
      opts: { loading: string; success: string; error: string },
    ) => {
      return toast.promise(fn, opts);
    },
    [],
  );

  return { success, error, info, promise };
}
