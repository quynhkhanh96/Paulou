import { useEffect, useRef, useState } from "react";
import { releaseFocus, takeFocus } from "./audioFocus";
import { PlayIcon, StopIcon } from "./icons";
import { TEXT } from "./learnerText";

// "Hear yourself": plays only the part of the learner's own recording that the
// recognizer heard for this word (D37 start_ms/end_ms), a little padded.
// The slice is cut from the decoded recording (Web Audio) rather than by
// seeking the <audio> element: a MediaRecorder file has no seek index, so
// seeking in it is unreliable (D65).

const PAD_S = 0.08;

const decodedCache = new WeakMap<Blob, Promise<AudioBuffer>>();
let context: AudioContext | null = null;

function audioContext(): AudioContext | null {
  if (context) return context;
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  context = Ctor ? new Ctor() : null;
  return context;
}

function decode(blob: Blob): Promise<AudioBuffer> {
  let decoded = decodedCache.get(blob);
  if (!decoded) {
    const ctx = audioContext();
    if (!ctx) return Promise.reject(new Error("no Web Audio"));
    decoded = blob.arrayBuffer().then((data) => ctx.decodeAudioData(data));
    decodedCache.set(blob, decoded);
    decoded.catch(() => decodedCache.delete(blob));
  }
  return decoded;
}

interface Props {
  recording: Blob | null;
  span: { startMs: number; endMs: number } | null;
}

export function HearYourself({ recording, span }: Props) {
  const [status, setStatus] = useState<"idle" | "loading" | "playing" | "error">("idle");
  const source = useRef<AudioBufferSourceNode | null>(null);
  const stop = useRef<() => void>(() => {});
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    stop.current = () => {
      const node = source.current;
      source.current = null;
      if (node) {
        node.onended = null;
        try {
          node.stop();
        } catch {
          /* already stopped */
        }
      }
      if (mounted.current) setStatus("idle");
    };
    const stopNow = stop.current;
    return () => {
      mounted.current = false;
      stopNow();
      releaseFocus(stopNow);
    };
  }, []);

  const unavailable = !recording || !span;
  const title = unavailable ? TEXT.noOwnClip : undefined;

  const toggle = async () => {
    if (!recording || !span) return;
    if (status === "playing" || status === "loading") {
      stop.current();
      return;
    }
    setStatus("loading");
    takeFocus(stop.current);
    try {
      const buffer = await decode(recording);
      if (!mounted.current) return;
      const ctx = audioContext()!;
      await ctx.resume();
      const start = Math.max(0, span.startMs / 1000 - PAD_S);
      const end = Math.min(buffer.duration, span.endMs / 1000 + PAD_S);
      if (end <= start) throw new Error("empty slice");
      const node = ctx.createBufferSource();
      node.buffer = buffer;
      node.connect(ctx.destination);
      node.onended = () => {
        source.current = null;
        if (mounted.current) setStatus("idle");
      };
      source.current = node;
      node.start(0, start, end - start);
      setStatus("playing");
    } catch {
      if (mounted.current) setStatus("error");
    }
  };

  return (
    <button
      type="button"
      className="btn btn-soft"
      onClick={() => void toggle()}
      disabled={unavailable}
      title={title}
      aria-pressed={status === "playing"}
    >
      {status === "playing" ? <StopIcon /> : <PlayIcon />}
      <span>{status === "error" ? "Could not play your recording" : status === "loading" ? "Loading…" : TEXT.hearYou}</span>
    </button>
  );
}
