import { useEffect, useRef, useState } from "react";
import { PlayIcon, StopIcon } from "./icons";

// One clip at a time: starting a clip stops the previous one.
let current: HTMLAudioElement | null = null;

interface Props {
  src: string;
  label: string;
  emoji?: string;
}

export function PlayButton({ src, label, emoji }: Props) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "playing" | "error">("idle");

  useEffect(
    () => () => {
      audio.current?.pause();
      if (current === audio.current) current = null;
    },
    [],
  );

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
    if (current && current !== audio.current) current.pause();
    const element = audio.current ?? new Audio(src);
    audio.current = element;
    current = element;
    element.onplaying = () => setStatus("playing");
    element.onended = () => setStatus("idle");
    element.onerror = () => setStatus("error");
    element.currentTime = 0;
    setStatus("loading");
    element.play().catch(() => setStatus("error"));
  };

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
