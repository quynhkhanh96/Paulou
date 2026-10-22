import type { Attempt, Health, Sentence, Speed, Target } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function parse<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T;
  let code = "unknown";
  let message = "Something went wrong. Try again.";
  try {
    const body = await response.json();
    if (body?.detail?.code) {
      code = body.detail.code;
      message = body.detail.message ?? message;
    } else if (Array.isArray(body?.detail)) {
      code = "invalid_request";
      message = "The request was not valid.";
    }
  } catch {
    /* non-JSON error body */
  }
  throw new ApiError(response.status, code, message);
}

async function send(input: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "network", "Could not reach the Paulou server. Is it running?");
  }
}

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  return parse<Health>(await send("/api/health", { signal }));
}

export async function createSentence(text: string, signal?: AbortSignal): Promise<Sentence> {
  return parse<Sentence>(
    await send("/api/sentences", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal,
    }),
  );
}

export function audioUrl(sentenceId: string, speed: Speed, target?: Target): string {
  const params = new URLSearchParams({ speed });
  if (target?.kind === "chunk") params.set("chunk", String(target.chunkIndex));
  if (target?.kind === "unit") params.set("unit", target.unitId);
  return `/api/sentences/${encodeURIComponent(sentenceId)}/audio?${params}`;
}

export async function createAttempt(
  sentenceId: string,
  target: Target,
  recording: Blob,
): Promise<Attempt> {
  const form = new FormData();
  form.set("sentence_id", sentenceId);
  if (target.kind === "chunk") form.set("chunk_index", String(target.chunkIndex));
  else form.set("unit_id", target.unitId);
  form.set("audio", recording, "attempt");
  return parse<Attempt>(await send("/api/attempts", { method: "POST", body: form }));
}
