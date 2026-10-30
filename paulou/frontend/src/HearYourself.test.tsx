import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HearYourself } from "./HearYourself";

const started: { when: number; offset: number; duration: number }[] = [];
const stopped = vi.fn();

class FakeNode {
  buffer: unknown = null;
  onended: (() => void) | null = null;
  connect = vi.fn();
  start(when: number, offset: number, duration: number) {
    started.push({ when, offset, duration });
  }
  stop() {
    stopped();
  }
}
class FakeContext {
  destination = {};
  decodeAudioData = vi.fn().mockResolvedValue({ duration: 2 });
  resume = vi.fn().mockResolvedValue(undefined);
  createBufferSource = () => new FakeNode();
}

// Blob.arrayBuffer is missing in jsdom
const recording = () => Object.assign(new Blob(["voice"]), { arrayBuffer: () => Promise.resolve(new ArrayBuffer(4)) });

beforeEach(() => {
  started.length = 0;
  stopped.mockClear();
  vi.resetModules();
  vi.stubGlobal("AudioContext", FakeContext);
});
afterEach(() => vi.unstubAllGlobals());

describe("HearYourself", () => {
  it("plays only the word's span of the recording, padded by 80 ms", async () => {
    const { HearYourself: Fresh } = await import("./HearYourself");
    const user = userEvent.setup();
    render(<Fresh recording={recording()} span={{ startMs: 500, endMs: 900 }} />);
    await user.click(screen.getByRole("button", { name: /hear yourself/i }));

    expect(await screen.findByRole("button", { pressed: true })).toBeInTheDocument();
    expect(started).toHaveLength(1);
    expect(started[0].offset).toBeCloseTo(0.42);
    expect(started[0].duration).toBeCloseTo(0.56);
  });

  it("never reads past the start or the end of the recording", async () => {
    const { HearYourself: Fresh } = await import("./HearYourself");
    const user = userEvent.setup();
    render(<Fresh recording={recording()} span={{ startMs: 20, endMs: 1990 }} />);
    await user.click(screen.getByRole("button", { name: /hear yourself/i }));
    await screen.findByRole("button", { pressed: true });
    expect(started[0].offset).toBe(0);
    expect(started[0].offset + started[0].duration).toBeCloseTo(2);
  });

  it("is disabled, with a reason, when none of the learner's sounds was found for the word", () => {
    render(<HearYourself recording={recording()} span={null} />);
    const button = screen.getByRole("button", { name: /hear yourself/i });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", expect.stringMatching(/none of your sounds/i));
  });

  it("says so when the recording cannot be decoded", async () => {
    class Broken extends FakeContext {
      decodeAudioData = vi.fn().mockRejectedValue(new Error("bad"));
    }
    vi.stubGlobal("AudioContext", Broken);
    const { HearYourself: Fresh } = await import("./HearYourself");
    const user = userEvent.setup();
    render(<Fresh recording={recording()} span={{ startMs: 0, endMs: 100 }} />);
    await user.click(screen.getByRole("button", { name: /hear yourself/i }));
    expect(await screen.findByText(/could not play your recording/i)).toBeInTheDocument();
  });

  it("stops when pressed again", async () => {
    const { HearYourself: Fresh } = await import("./HearYourself");
    const user = userEvent.setup();
    render(<Fresh recording={recording()} span={{ startMs: 0, endMs: 100 }} />);
    await user.click(screen.getByRole("button", { name: /hear yourself/i }));
    await user.click(await screen.findByRole("button", { pressed: true }));
    expect(stopped).toHaveBeenCalled();
  });
});
