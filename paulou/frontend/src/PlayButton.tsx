import { useEffect, useRef, useState } from "react";
import { releaseFocus, takeFocus } from "./audioFocus";
import { PlayIcon, StopIcon } from "./icons";

interface Props {
  src: string;
  label: string;
  emoji?: string;
  /** Icon-only round button; `label` becomes its accessible name. */
  compact?: boolean;
}

export function PlayButton({ src, label, emoji, compact }: Props) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const stop = useRef<() => void>(() => {});
  const mounted = useRef(true);
  const [status, setStatus] = useState<"idle" | "loading" | "playing" | "error">("idle");

  useEffect(() => {
    mounted.current = true;
    stop.current = () => {
      audio.current?.pause();
      if (mounted.current) setStatus("idle");
    };
    const stopNow = stop.current;
    return () => {
      mounted.current = false;
      audio.current?.pause();
      releaseFocus(stopNow);
    };
  }, []);

  // A different clip (another chunk or unit) starts from scratch.
  useEffect(() => {
    audio.current?.pause();
    audio.current = null;
    setStatus("idle");
  }, [src]);

  const toggle = () => {
    if (status === "playing" || status === "loading") {
      audio.current?.pause();
      setStatus("idle");
      return;
    }
    takeFocus(stop.current);
    const element = audio.current ?? new Audio(src);
    audio.current = element;
    element.onplaying = () => setStatus("playing");
    element.onended = () => setStatus("idle");
    element.onerror = () => setStatus("error");
    element.currentTime = 0;
    setStatus("loading");
    element.play().catch(() => setStatus("error"));
  };

  if (compact) {
    return (
      <button
        type="button"
        className={`btn btn-soft btn-icon ${status === "error" ? "is-error" : ""}`}
        onClick={toggle}
        aria-pressed={status === "playing"}
        aria-label={status === "error" ? `${label} (audio unavailable)` : label}
        title={status === "error" ? "Audio unavailable" : label}
      >
        {status === "playing" ? <StopIcon /> : status === "error" ? <span aria-hidden="true">!</span> : <PlayIcon />}
      </button>
    );
  }

  return (
    <button type="button" className="btn btn-soft" onClick={toggle} aria-pressed={status === "playing"}>
      {status === "playing" ? <StopIcon /> : <PlayIcon />}
      <span>
        {emoji && <span aria-hidden="true">{emoji} </span>}
        {status === "error" ? "Audio unavailable" : status === "loading" ? "Loading…" : label}
      </span>
    </button>
  );
}
