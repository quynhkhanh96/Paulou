import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import * as api from "./api";
import { ATTEMPT, SENTENCE } from "./fixtures";

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

    expect(await screen.findByRole("button", { name: "les amis" })).toBeInTheDocument();
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

    await user.click(await screen.findByRole("button", { name: "les amis" }));
    await user.click(screen.getByRole("button", { name: /record this chunk/i }));
    expect(recorderCalls.start).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: /stop and check/i }));

    await waitFor(() => expect(mocked.createAttempt).toHaveBeenCalledTimes(1));
    const [sentenceId, target, blob] = mocked.createAttempt.mock.calls[0];
    expect([sentenceId, target]).toEqual(["abc123", { kind: "chunk", chunkIndex: 1 }]);
    expect(blob).toBeInstanceOf(Blob);

    const strip = await screen.findByRole("list", { name: /sound by sound/i });
    expect(strip.querySelectorAll("li")).toHaveLength(5);
    expect(screen.getByText(/Missing the z sound/)).toBeInTheDocument();
    expect(screen.getByText(/links this word to the next chunk/i)).toBeInTheDocument();
    expect(screen.getByText(/placeholder until scoring is calibrated/i)).toBeInTheDocument();
    expect(screen.queryByText(/\d+\s*\/\s*100/)).not.toBeInTheDocument(); // no numeric score
  });

  it("drills a single unit: the attempt targets the unit, not the chunk", async () => {
    mocked.createSentence.mockResolvedValue(SENTENCE);
    mocked.createAttempt.mockResolvedValue({ ...ATTEMPT, chunk_index: null, unit_id: "c1_unit_0" });
    const user = await prepareSentence();

    await user.click(await screen.findByRole("button", { name: "les amis" }));
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
});
