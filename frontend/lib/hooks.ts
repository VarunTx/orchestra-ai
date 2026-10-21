import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";

export type Resource<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => Promise<void>;
  setData: (value: T) => void;
};

/** Small data hook: explicit loading/error state, optional polling, no retries that hide failures. */
export function useApi<T>(
  path: string | null,
  options?: { pollMs?: number },
): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const request = useRef<AbortController | null>(null);
  const pollMs = options?.pollMs;

  const reload = useCallback(async () => {
    if (!path) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    try {
      const result = await api<T>(path, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setData(result);
      setError(null);
    } catch (exception) {
      if (controller.signal.aborted) return;
      setError((exception as ApiError).message);
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    setData(null);
    setError(null);
    setLoading(true);
    void reload();
    return () => {
      request.current?.abort();
    };
  }, [reload]);

  useEffect(() => {
    if (!pollMs || !path) return;
    const timer = setInterval(() => void reload(), pollMs);
    return () => clearInterval(timer);
  }, [pollMs, path, reload]);

  return { data, error, loading, reload, setData };
}
