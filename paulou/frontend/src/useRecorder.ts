import { useCallback, useRef, useState } from "react";

export type RecorderState = "idle" | "recording" | "denied" | "unsupported";

const CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

export function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type));
}

export interface Recorder {
  state: RecorderState;
  start: () => Promise<void>;
  stop: () => Promise<Blob | null>;
}

// The backend converts whatever container the browser produced (webm/opus in
// Chromium, mp4 in Safari) to WAV, so no format is forced here.
export function useRecorder(): Recorder {
  const [state, setState] = useState<RecorderState>("idle");
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);

  const start = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setState("unsupported");
      return;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setState("denied");
      return;
    }
    const mimeType = pickMimeType();
    const instance = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    chunks.current = [];
    instance.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.current.push(event.data);
    };
    instance.start();
    recorder.current = instance;
    setState("recording");
  }, []);

  const stop = useCallback(async () => {
    const instance = recorder.current;
    if (!instance || instance.state === "inactive") return null;
    const finished = new Promise<Blob>((resolve) => {
      instance.onstop = () => resolve(new Blob(chunks.current, { type: instance.mimeType }));
    });
    instance.stop();
    instance.stream.getTracks().forEach((track) => track.stop());
    recorder.current = null;
    setState("idle");
    return finished;
  }, []);

  return { state, start, stop };
}
