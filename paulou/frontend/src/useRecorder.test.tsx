import { act, renderHook } from "@testing-library/react";
import { pickMimeType, useRecorder } from "./useRecorder";

class FakeRecorder {
  static supported = ["audio/webm;codecs=opus", "audio/mp4"];
  static isTypeSupported = (t: string) => FakeRecorder.supported.includes(t);
  static last: FakeRecorder;
  state: "inactive" | "recording" = "inactive";
  mimeType: string;
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(public stream: MediaStream, options?: { mimeType?: string }) {
    this.mimeType = options?.mimeType ?? "";
    FakeRecorder.last = this;
  }
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["voice"], { type: this.mimeType }) });
    this.onstop?.();
  }
}

const track = { stop: vi.fn() };
const stream = { getTracks: () => [track] } as unknown as MediaStream;

beforeEach(() => {
  track.stop.mockClear();
  FakeRecorder.supported = ["audio/webm;codecs=opus", "audio/mp4"];
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("pickMimeType", () => {
  it("prefers webm/opus (Chromium, Firefox)", () => {
    expect(pickMimeType()).toBe("audio/webm;codecs=opus");
  });
  it("falls back to mp4 (Safari)", () => {
    FakeRecorder.supported = ["audio/mp4"];
    expect(pickMimeType()).toBe("audio/mp4");
  });
  it("returns undefined when nothing matches so the browser default is used", () => {
    FakeRecorder.supported = [];
    expect(pickMimeType()).toBeUndefined();
  });
});

describe("useRecorder", () => {
  it("records, stops the microphone tracks and returns a typed blob", async () => {
    const { result } = renderHook(() => useRecorder());
    await act(() => result.current.start());
    expect(result.current.state).toBe("recording");

    let blob: Blob | null = null;
    await act(async () => {
      blob = await result.current.stop();
    });

    expect(blob).not.toBeNull();
    expect(blob!.size).toBeGreaterThan(0);
    expect(blob!.type).toBe("audio/webm;codecs=opus");
    expect(track.stop).toHaveBeenCalled();
    expect(result.current.state).toBe("idle");
  });

  it("reports a refused permission", async () => {
    (navigator.mediaDevices.getUserMedia as ReturnType<typeof vi.fn>).mockRejectedValue(new DOMException("no", "NotAllowedError"));
    const { result } = renderHook(() => useRecorder());
    await act(() => result.current.start());
    expect(result.current.state).toBe("denied");
  });

  it("reports a browser without MediaRecorder", async () => {
    vi.stubGlobal("MediaRecorder", undefined);
    const { result } = renderHook(() => useRecorder());
    await act(() => result.current.start());
    expect(result.current.state).toBe("unsupported");
  });

  it("stop without a recording returns null", async () => {
    const { result } = renderHook(() => useRecorder());
    let blob: Blob | null = new Blob();
    await act(async () => {
      blob = await result.current.stop();
    });
    expect(blob).toBeNull();
  });
});
