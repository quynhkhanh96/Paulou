import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { guideAudioUrl } from "./api";
import { Guide } from "./Guide";
import { GUIDE } from "./guideData";

describe("Guide", () => {
  it("renders every section with a heading and its sounds", () => {
    render(<Guide />);
    for (const section of GUIDE) {
      expect(screen.getByRole("heading", { name: section.title })).toBeInTheDocument();
    }
    expect(screen.getByRole("heading", { name: "/y/" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "/ɑ̃/" })).toBeInTheDocument();
  });

  it("shows examples with their IPA and meaning", () => {
    render(<Guide />);
    const card = screen.getByRole("heading", { name: "/y/" }).closest("article")!;
    const examples = within(card).getByRole("list", { name: "Examples" });
    expect(within(examples).getByText("tu")).toBeInTheDocument();
    expect(examples).toHaveTextContent("/ty/");
  });
});

describe("Guide audio", () => {
  it("gives every example its own play button, and none to the sound itself", () => {
    render(<Guide />);
    const card = screen.getByRole("heading", { name: "/i/" }).closest("article")!;
    const buttons = within(card).getAllByRole("button");
    expect(buttons.map((b) => b.getAttribute("aria-label"))).toEqual([
      'Listen to "si"',
      'Listen to "vie"',
      'Listen to "ici"',
    ]);
  });

  it("plays the word through the guide endpoint", async () => {
    const play = vi.fn().mockResolvedValue(undefined);
    const sources: string[] = [];
    vi.stubGlobal(
      "Audio",
      class {
        onplaying: (() => void) | null = null;
        currentTime = 0;
        constructor(src: string) {
          sources.push(src);
        }
        play = play;
        pause = vi.fn();
      },
    );
    render(<Guide />);
    const card = screen.getByRole("heading", { name: "/y/" }).closest("article")!;
    await userEvent.click(within(card).getByRole("button", { name: 'Listen to "rue"' }));

    expect(sources).toEqual(["/api/guide/audio?text=rue"]);
    expect(play).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });

  it("encodes apostrophes and spaces in the URL", () => {
    expect(guideAudioUrl("l'ami")).toBe("/api/guide/audio?text=l%27ami");
    expect(guideAudioUrl("les amis")).toBe("/api/guide/audio?text=les+amis");
  });
});

describe("guide data", () => {
  const sounds = GUIDE.flatMap((s) => s.sounds);

  it("has unique ids", () => {
    expect(new Set(sounds.map((s) => s.id)).size).toBe(sounds.length);
    expect(new Set(GUIDE.map((s) => s.id)).size).toBe(GUIDE.length);
  });

  it("covers the whole French phoneme inventory", () => {
    const symbols = GUIDE.filter((s) => ["vowels", "nasals", "glides", "consonants"].includes(s.id))
      .flatMap((s) => s.sounds.map((x) => x.symbol))
      .join(" ")
      .match(/[^\s/·]+/gu)!;
    const expected = "i e ɛ a ɔ o u y ø œ ə ɑ̃ ɔ̃ ɛ̃ œ̃ j w ɥ p t k b d g f v s z ʃ ʒ m n ɲ l ʁ".split(" ");
    for (const phoneme of expected) expect(symbols).toContain(phoneme);
  });

  it("gives every sound at least one example, apart from the rhythm note", () => {
    for (const sound of sounds.filter((s) => s.id !== "rhythm")) expect(sound.examples.length).toBeGreaterThan(0);
  });

  it("every example word can be sent to the audio endpoint (letters, spaces, apostrophes, hyphens, at most 40 characters)", () => {
    for (const example of sounds.flatMap((s) => s.examples)) {
      expect(example.word).toMatch(/^[\p{L}]+(?:[ '’-][\p{L}]+)*$/u);
      expect(example.word.length).toBeLessThanOrEqual(40);
    }
  });

  it("every IPA transcription uses only symbols without stray spaces or slashes", () => {
    for (const example of sounds.flatMap((s) => s.examples)) {
      expect(example.ipa).not.toMatch(/[\s/]/);
    }
  });
});
