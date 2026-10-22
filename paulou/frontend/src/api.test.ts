import { ApiError, audioUrl, createAttempt, createSentence } from "./api";
import { SENTENCE } from "./fixtures";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

afterEach(() => vi.restoreAllMocks());

describe("audioUrl", () => {
  it("addresses the whole sentence, a chunk or a unit", () => {
    expect(audioUrl("s1", "normal")).toBe("/api/sentences/s1/audio?speed=normal");
    expect(audioUrl("s1", "slow", { kind: "chunk", chunkIndex: 2 })).toBe("/api/sentences/s1/audio?speed=slow&chunk=2");
    expect(audioUrl("s1", "normal", { kind: "unit", unitId: "c0_unit_1" })).toBe(
      "/api/sentences/s1/audio?speed=normal&unit=c0_unit_1",
    );
  });
});

describe("createSentence", () => {
  it("posts the text and returns the parsed sentence", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, SENTENCE));
    const result = await createSentence("Bonjour les amis");
    expect(result.sentence_id).toBe("abc123");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sentences");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ text: "Bonjour les amis" });
  });

  it("turns the backend error body into an ApiError with its code and message", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      json(422, { detail: { code: "text_not_supported", message: "Write numbers as words." } }),
    );
    await expect(createSentence("3")).rejects.toMatchObject({ status: 422, code: "text_not_supported", message: "Write numbers as words." });
  });

  it("reports an unreachable server instead of a raw TypeError", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const error = await createSentence("x").catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("network");
  });

  it("falls back to a generic message for a non-JSON error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("<html>502</html>", { status: 502 }));
    await expect(createSentence("x")).rejects.toMatchObject({ status: 502, code: "unknown" });
  });
});

describe("createAttempt", () => {
  const blob = new Blob(["abc"], { type: "audio/webm" });

  it("sends a chunk target as chunk_index", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, { results: [] }));
    await createAttempt("s1", { kind: "chunk", chunkIndex: 1 }, blob);
    const form = (fetchMock.mock.calls[0][1] as RequestInit).body as FormData;
    expect(form.get("sentence_id")).toBe("s1");
    expect(form.get("chunk_index")).toBe("1");
    expect(form.has("unit_id")).toBe(false);
    expect(form.get("audio")).toBeInstanceOf(Blob);
  });

  it("sends a unit target as unit_id", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, { results: [] }));
    await createAttempt("s1", { kind: "unit", unitId: "c0_unit_0" }, blob);
    const form = (fetchMock.mock.calls[0][1] as RequestInit).body as FormData;
    expect(form.get("unit_id")).toBe("c0_unit_0");
    expect(form.has("chunk_index")).toBe(false);
  });
});
