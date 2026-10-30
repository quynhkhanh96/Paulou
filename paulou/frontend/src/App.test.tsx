import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import * as api from "./api";
import { ATTEMPT, SENTENCE, SENTENCE_ATTEMPT } from "./fixtures";

vi.mock("./api", async (importOriginal) => ({ ...(await importOriginal<typeof import("./api")>()), getHealth: vi.fn(), createSentence: vi.fn(), createAttempt: vi.fn() }));

const recorderCalls = { start: vi.fn(), stop: vi.fn() };
vi.mock("./useRecorder", async () => {
  const { useState } = await import("react");
  return {
    useRecorder: () => {
      const [state, setState] = useState<"idle" | "recording">("idle");
      return {
        state,
        start: async () => {
          recorderCalls.start();
          setState("recording");
        },
        stop: async () => {
          setState("idle");
          return recorderCalls.stop();
        },
      };
    },
  };
});

const mocked = vi.mocked(api);
const ready = { status: "ready" as const, calibrated: false, detail: null };

beforeEach(() => {
  vi.clearAllMocks();
  mocked.getHealth.mockResolvedValue(ready);
  recorderCalls.stop.mockReturnValue(new Blob(["voice"], { type: "audio/webm" }));
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() }));
});

async function prepareSentence() {
  const user = userEvent.setup();
  render(<App />);
  await user.type(screen.getByLabelText(/which sentence/i), "Bonjour les amis");
  await user.click(screen.getByRole("button", { name: /prepare/i }));
  return user;
}

describe("App", () => {
  it("disables Prepare for blank text", async () => {
    await act(async () => {
      render(<App />);
    });
    expect(screen.getByRole("button", { name: /prepare/i })).toBeDisabled();
  });

  it("shows a loading state while the sentence is prepared, then the practice screen", async () => {
    let resolve!: (s: typeof SENTENCE) => void;
    mocked.createSentence.mockReturnValue(new Promise((r) => (resolve = r)));
    await prepareSentence();

    expect(screen.getByRole("status")).toHaveTextContent(/preparing your sentence/i);
    resolve(SENTENCE);

    expect(await screen.findByRole("tab", { name: "les amis" })).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows the server's message when preparation fails and keeps the text", async () => {
    mocked.createSentence.mockRejectedValue(new api.ApiError(422, "text_not_supported", "Write numbers as words."));
    await prepareSentence();

    expect(await screen.findByRole("alert")).toHaveTextContent("Write numbers as words.");
    expect(screen.getByLabelText(/which sentence/i)).toHaveValue("Bonjour les amis");
  });

  it("cancelling the preparation returns to the form", async () => {
    mocked.createSentence.mockReturnValue(new Promise(() => {}));
    const user = await prepareSentence();
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.getByLabelText(/which sentence/i)).toBeInTheDocument();
  });

  it("records a chunk, sends it, and renders ops, feedback and the limitation hints", async () => {
    mocked.createSentence.mockResolvedValue(SENTENCE);
    mocked.createAttempt.mockResolvedValue(ATTEMPT);
    const user = await prepareSentence();

    await user.click(await screen.findByRole("tab", { name: "les amis" }));
    await user.click(screen.getByRole("button", { name: /record this chunk/i }));
    expect(recorderCalls.start).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: /stop and check/i }));

    await waitFor(() => expect(mocked.createAttempt).toHaveBeenCalledTimes(1));
    const [sentenceId, target, blob] = mocked.createAttempt.mock.calls[0];
    expect([sentenceId, target]).toEqual(["abc123", { kind: "chunk", chunkIndex: 1 }]);
    expect(blob).toBeInstanceOf(Blob);

    const strip = await screen.findByRole("list", { name: /sound by sound/i });
    expect(strip.querySelectorAll("li")).toHaveLength(5);
    expect(screen.getAllByText(/missing/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/links this word to the next chunk/i)).toBeInTheDocument();
    expect(screen.queryByText(/\d+\s*\/\s*100/)).not.toBeInTheDocument(); // no numeric score
  });

  it("drills a single unit: the attempt targets the unit, not the chunk", async () => {
    mocked.createSentence.mockResolvedValue(SENTENCE);
    mocked.createAttempt.mockResolvedValue({ ...ATTEMPT, chunk_index: null, unit_id: "c1_unit_0" });
    const user = await prepareSentence();

    await user.click(await screen.findByRole("tab", { name: "les amis" }));
    await user.click(screen.getByRole("button", { name: /^les amis \/lezami\/ liaison \/z\/$/ }));
    await user.click(screen.getByRole("button", { name: /record "les amis"/i }));
    await user.click(screen.getByRole("button", { name: /stop and check/i }));

    await waitFor(() => expect(mocked.createAttempt).toHaveBeenCalled());
    expect(mocked.createAttempt.mock.calls[0][1]).toEqual({ kind: "unit", unitId: "c1_unit_0" });
  });

  it("shows a server error and offers to prepare again when the sentence has expired", async () => {
    mocked.createSentence.mockResolvedValue(SENTENCE);
    mocked.createAttempt.mockRejectedValue(new api.ApiError(404, "sentence_not_found", "This sentence is no longer prepared. Prepare it again."));
    const user = await prepareSentence();

    await user.click(screen.getByRole("button", { name: /record this chunk/i }));
    await user.click(screen.getByRole("button", { name: /stop and check/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/no longer prepared/i);

    await user.click(screen.getByRole("button", { name: /prepare again/i }));
    await waitFor(() => expect(mocked.createSentence).toHaveBeenCalledTimes(2));
  });

  it("locks recording until the speech model is ready", async () => {
    mocked.getHealth.mockResolvedValue({ status: "warming_up", calibrated: false, detail: null });
    mocked.createSentence.mockResolvedValue(SENTENCE);
    await prepareSentence();

    expect(await screen.findByRole("button", { name: /record this chunk/i })).toBeDisabled();
    expect(screen.getAllByText(/speech model is still loading/i).length).toBeGreaterThan(0);
  });

  it("practises the whole sentence from its own tab and groups the results by chunk", async () => {
    mocked.createSentence.mockResolvedValue(SENTENCE);
    mocked.createAttempt.mockResolvedValue(SENTENCE_ATTEMPT);
    const user = await prepareSentence();

    await user.click(await screen.findByRole("tab", { name: "Whole sentence" }));
    expect(screen.getByRole("tab", { name: "Whole sentence" })).toHaveAttribute("aria-selected", "true");
    await user.click(screen.getByRole("button", { name: /record the whole sentence/i }));
    await user.click(screen.getByRole("button", { name: /stop and check/i }));

    await waitFor(() => expect(mocked.createAttempt).toHaveBeenCalledTimes(1));
    expect(mocked.createAttempt.mock.calls[0][1]).toEqual({ kind: "sentence" });
    expect(await screen.findByRole("group", { name: "Chunk 1: Bonjour" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Chunk 2: les amis" })).toBeInTheDocument();
    // the first word that needs work is open; the all-correct one stays closed
    expect(screen.getAllByRole("list", { name: /sound by sound/i })).toHaveLength(1);
    expect(document.querySelector(".score")).toHaveTextContent("1/2 words correct");
  });

  it("clears the previous result when another tab is chosen", async () => {
    mocked.createSentence.mockResolvedValue(SENTENCE);
    mocked.createAttempt.mockResolvedValue(ATTEMPT);
    const user = await prepareSentence();
    await user.click(screen.getByRole("button", { name: /record this chunk/i }));
    await user.click(screen.getByRole("button", { name: /stop and check/i }));
    await screen.findByRole("list", { name: /sound by sound/i });

    await user.click(screen.getByRole("tab", { name: "Whole sentence" }));
    expect(screen.queryByRole("list", { name: /sound by sound/i })).not.toBeInTheDocument();
  });

  it("chunk tabs are tabs of a tablist and arrow keys move between them", async () => {
    mocked.createSentence.mockResolvedValue(SENTENCE);
    const user = await prepareSentence();

    const tablist = await screen.findByRole("tablist", { name: /what to practice/i });
    expect(within(tablist).getAllByRole("tab").map((t) => t.textContent?.replace(/^\d/, ""))).toEqual([
      "Bonjour",
      "les amis",
      "Whole sentence",
    ]);
    await user.click(screen.getByRole("tab", { name: "Bonjour" }));
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "les amis" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Whole sentence" })).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Bonjour" })).toHaveAttribute("aria-selected", "true");
  });

  it("opens the pronunciation guide without losing the practice state", async () => {
    mocked.createSentence.mockResolvedValue(SENTENCE);
    mocked.createAttempt.mockResolvedValue(ATTEMPT);
    const user = await prepareSentence();
    await user.click(screen.getByRole("button", { name: /record this chunk/i }));
    await user.click(screen.getByRole("button", { name: /stop and check/i }));
    await screen.findByRole("list", { name: /sound by sound/i });

    await user.click(screen.getByRole("tab", { name: "Pronunciation guide" }));
    expect(screen.getByRole("heading", { name: "Oral vowels" })).toBeVisible();
    expect(screen.getByRole("list", { name: /sound by sound/i, hidden: true })).not.toBeVisible();

    await user.click(screen.getByRole("tab", { name: "Practice" }));
    expect(screen.getByRole("list", { name: /sound by sound/i })).toBeVisible();
  });

  it("the guide is available from the start page", async () => {
    await act(async () => {
      render(<App />);
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Pronunciation guide" }));
    expect(screen.getByRole("heading", { name: "Nasal vowels" })).toBeVisible();
    expect(screen.getByLabelText(/which sentence/i)).not.toBeVisible();
  });
});
