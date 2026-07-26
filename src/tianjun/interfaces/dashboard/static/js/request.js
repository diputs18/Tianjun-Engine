export class RequestTimeoutError extends Error {
  constructor(operation, timeoutMs) {
    super(`${operation} 请求超时（${timeoutMs}ms）`);
    this.name = "RequestTimeoutError";
  }
}

export async function requestJson(path, options = {}) {
  const operation = `${options.method || "GET"} ${path}`;
  const timeoutMs = Math.max(100, Number(options.timeoutMs ?? 8000));
  const controller = new AbortController();
  const upstream = options.signal;
  const relayAbort = () => controller.abort(upstream.reason);
  if (upstream?.aborted) relayAbort();
  else upstream?.addEventListener("abort", relayAbort, { once: true });
  const timer = setTimeout(
    () => controller.abort(new RequestTimeoutError(operation, timeoutMs)),
    timeoutMs,
  );
  try {
    const response = await (options.fetchImpl || fetch)(path, {
      method: options.method || "GET",
      headers: options.body === undefined ? options.headers : {
        "Content-Type": "application/json",
        ...options.headers,
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    });
    if (!response.ok) throw await responseError(response, operation);
    return response.json();
  } catch (error) {
    if (controller.signal.reason instanceof RequestTimeoutError) {
      throw controller.signal.reason;
    }
    throw error;
  } finally {
    clearTimeout(timer);
    upstream?.removeEventListener("abort", relayAbort);
  }
}

export async function responseError(response, operation) {
  let detail = "";
  try {
    const payload = await response.json();
    detail = payload.error || payload.message || payload.validation?.errors?.[0]?.reason || JSON.stringify(payload);
  } catch (_) {
    detail = await response.text();
  }
  return new Error(`${operation} -> ${response.status}${detail ? `: ${detail}` : ""}`);
}
