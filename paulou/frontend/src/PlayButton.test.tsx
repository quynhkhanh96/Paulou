import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PlayButton } from "./PlayButton";

class FakeAudio {
  static instances: FakeAudio[] = [];
  onplaying: (() => void) | null = null;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  currentTime = 0;
  paused = true;
  fail = false;
  constructor(public src: string) {
    FakeAudio.instances.push(this);
  }
  play() {
    this.paused = false;
    if (this.fail) return Promise.reject(new Error("blocked"));
    queueMicrotask(() => this.onplaying?.());
    return Promise.resolve();
  }
  pause() {
    this.paused = true;
  }
}

beforeEach(() => {
  FakeAudio.instances = [];
  vi.stubGlobal("Audio", FakeAudio);
});
afterEach(() => vi.unstubAllGlobals());

describe("PlayButton", () => {
  it("plays its clip and shows the playing state", async () => {
    const user = userEvent.setup();
    render(<PlayButton src="/clip-a" label="Listen" />);
    await user.click(screen.getByRole("button", { name: /listen/i }));
    expect(FakeAudio.instances[0].src).toBe("/clip-a");
    expect(await screen.findByRole("button", { pressed: true })).toBeInTheDocument();
  });

  it("starting another clip stops the first", async () => {
    const user = userEvent.setup();
    render(
      <>
        <PlayButton src="/a" label="First" />
        <PlayButton src="/b" label="Second" />
      </>,
    );
    await user.click(screen.getByRole("button", { name: /first/i }));
    await user.click(screen.getByRole("button", { name: /second/i }));
    expect(FakeAudio.instances[0].paused).toBe(true);
    expect(FakeAudio.instances[1].paused).toBe(false);
  });

  it("says so when the clip cannot be played", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "Audio",
      class extends FakeAudio {
        fail = true;
      },
    );
    render(<PlayButton src="/gone" label="Listen" />);
    await user.click(screen.getByRole("button"));
    expect(await screen.findByText(/audio unavailable/i)).toBeInTheDocument();
  });
});
