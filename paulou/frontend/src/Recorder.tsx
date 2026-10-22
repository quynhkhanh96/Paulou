import { MicIcon, StopIcon } from "./icons";
import type { RecorderState } from "./useRecorder";

interface Props {
  state: RecorderState;
  disabled: boolean;
  busy: boolean;
  onStart: () => void;
  onStop: () => void;
  idleLabel: string;
}

export function RecordButton({ state, disabled, busy, onStart, onStop, idleLabel }: Props) {
  const recording = state === "recording";
  return (
    <div className="record">
      <button
        type="button"
        className={`btn btn-primary ${recording ? "is-recording" : ""}`}
        disabled={disabled || busy}
        onClick={recording ? onStop : onStart}
      >
        {recording ? <StopIcon /> : <MicIcon />}
        <span>{busy ? "Checking…" : recording ? "Stop and check" : idleLabel}</span>
      </button>
      {state === "denied" && (
        <p className="note warn" role="alert">
          The browser blocked the microphone. Allow microphone access for this site, then press record again.
        </p>
      )}
      {state === "unsupported" && (
        <p className="note warn" role="alert">
          This browser cannot record audio here. Use a current Chrome, Edge, Firefox or Safari on localhost or https.
        </p>
      )}
    </div>
  );
}
