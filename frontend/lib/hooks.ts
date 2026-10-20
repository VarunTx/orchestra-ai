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
export function useApi<T>(path: string | null, options?: { pollMs?: number }): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const mounted = useRef(true);
  const pollMs = options?.pollMs;

  const reload = useCallback(async () => {
    if (!path) return;
    try {
      const result = await api<T>(path);
      if (!mounted.current) return;
      setData(result);
      setError(null);
    } catch (exception) {
      if (!mounted.current) return;
      setError((exception as ApiError).message);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    mounted.current = true;
    setLoading(true);
    void reload();
    return () => {
      mounted.current = false;
    };
  }, [reload]);

  useEffect(() => {
    if (!pollMs || !path) return;
    const timer = setInterval(() => void reload(), pollMs);
    return () => clearInterval(timer);
  }, [pollMs, path, reload]);

  return { data, error, loading, reload, setData };
}
