export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

const DEFAULT_TIMEOUT = 30_000;

export async function request<T>(
  url: string,
  options: RequestInit & { timeout?: number } = {}
): Promise<T> {
  const { timeout = DEFAULT_TIMEOUT, ...rest } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const res = await fetch(url, {
      ...rest,
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try {
        const body = await res.json();
        if (body.detail) detail = body.detail;
      } catch {
        // ignore parse error
      }
      throw new ApiError(res.status, detail);
    }

    // For 204 No Content
    if (res.status === 204) {
      return undefined as T;
    }

    try {
      return (await res.json()) as T;
    } catch {
      return undefined as T;
    }
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "请求超时，请重试");
    }
    throw new ApiError(0, err instanceof Error ? err.message : "网络错误");
  }
}
