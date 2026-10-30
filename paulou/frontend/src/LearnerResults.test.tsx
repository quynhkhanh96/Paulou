import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LearnerResults } from "./LearnerResults";
import { op, SENTENCE } from "./fixtures";
import type { Attempt } from "./types";

const attempt = (results: Attempt["results"], whole = false): Attempt => ({
  sentence_id: "abc123",
  chunk_index: null,
  unit_id: null,
  whole_sentence: whole,
  calibrated: false,
  results,
});
const unitResult = (unit_id: string, ops: ReturnType<typeof op>[]) => ({ unit_id, score: null, feedback_text: "", ops });

const BONJOUR = unitResult("c0_unit_0", [
  op("match", "b", "b"),
  op("substitution", "ɔ̃", "o", "S_near", ["missing_nasality", "not_open_enough"], 50),
  op("match", "ʒ", "ʒ", "M", [], 100),
  op("deletion", "u", null),
  op("substitution", "ʁ", "l", "S", [], 150),
]);
const LES_AMIS = unitResult("c1_unit_0", [op("match", "l", "l"), op("match", "e", "e"), op("match", "z", "z"), op("match", "a", "a")]);

const itemText = (li: HTMLElement) => li.lastElementChild!.textContent;
const summaryBox = (title: string) => screen.getAllByRole("heading", { name: title })[0].closest<HTMLElement>(".box")!;

const renderResults = (a: Attempt, recording: Blob | null = new Blob(["x"])) =>
  render(<LearnerResults attempt={a} sentence={SENTENCE} recording={recording} recordingUrl={null} />);

describe("LearnerResults", () => {
  it("opens with the score line and counts", () => {
    renderResults(attempt([BONJOUR, LES_AMIS]));
    const score = document.querySelector<HTMLElement>(".score")!;
    expect(score).toHaveTextContent("1/2 words correct");
    expect(score).toHaveTextContent("6/9 sounds correct · 1 close");
  });

  it("shows 'Needs fixing' before 'You did well', far mistakes first, with concrete sentences", () => {
    renderResults(attempt([BONJOUR, LES_AMIS]));
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings.indexOf("Needs fixing")).toBeLessThan(headings.indexOf("You did well"));

    const fix = summaryBox("Needs fixing");
    const items = within(fix).getAllByRole("listitem").map(itemText);
    expect(items).toHaveLength(2);
    expect(items[0]).toBe("missing /u/ in Bonjour");
    expect(items[1]).toBe("/ʁ/ in Bonjour was heard as /l/");
    expect(within(fix).getByText("1 more point, see them in each word.")).toBeInTheDocument();
  });

  it("describes a close sound with the feature that is off", () => {
    renderResults(attempt([unitResult("c0_unit_0", [op("substitution", "ɔ̃", "o", "S_near", ["missing_nasality"])]), LES_AMIS]));
    expect(itemText(screen.getAllByText(/is close, heard as/)[0].closest("li")!)).toBe("/ɔ̃/ in Bonjour is close, heard as /o/: missing nasality");
  });

  it("is specific about what was done well", () => {
    renderResults(attempt([BONJOUR, LES_AMIS]));
    const items = within(summaryBox("You did well")).getAllByRole("listitem").map(itemText);
    expect(items[0]).toBe("/ʒ/ in Bonjour is correct, a sound many learners find hard");
    expect(items[1]).toBe("les amis correct");
  });

  it("hides an empty box and lets the other one fill the width", () => {
    renderResults(attempt([unitResult("c0_unit_0", [op("match", "b", "b")]), LES_AMIS]));
    expect(screen.queryByRole("heading", { name: "Needs fixing" })).not.toBeInTheDocument();
    expect(screen.getByText("Everything is correct")).toBeInTheDocument();
    expect(document.querySelector(".cols")).toHaveClass("single");

  });

  it("a box that is the only one takes the whole width", () => {
    renderResults(attempt([unitResult("c0_unit_0", [op("deletion", "b", null)]), unitResult("c1_unit_0", [op("deletion", "l", null)])]));
    expect(screen.queryByRole("heading", { name: "You did well" })).not.toBeInTheDocument();
    expect(summaryBox("Needs fixing").closest(".cols")).toHaveClass("single");
  });

  it("gives every word a chip with its state and opens the first one that needs work", () => {
    renderResults(attempt([BONJOUR, LES_AMIS]));
    const bonjour = screen.getByRole("button", { name: /^Bonjour/ });
    const lesAmis = screen.getByRole("button", { name: /^les amis/ });
    expect(bonjour).toHaveClass("err");
    expect(bonjour).toHaveTextContent("3 errors");
    expect(bonjour).toHaveAttribute("aria-expanded", "true");
    expect(lesAmis).toHaveClass("ok");
    expect(lesAmis).toHaveAttribute("aria-expanded", "false");
  });

  it("a word whose only mistakes are close ones is 'close'", () => {
    renderResults(attempt([unitResult("c0_unit_0", [op("substitution", "z", "s", "S_near", ["missing_voicing"])]), LES_AMIS]));
    const chip = screen.getByRole("button", { name: /^Bonjour/ });
    expect(chip).toHaveClass("near");
    expect(chip).toHaveTextContent("close");
  });

  it("opens a word's card in place, one at a time, and closes it again", async () => {
    const user = userEvent.setup();
    renderResults(attempt([BONJOUR, LES_AMIS]));
    expect(screen.getAllByRole("region", { name: /^Details:/ })).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: /^les amis/ }));
    const card = screen.getByRole("region", { name: "Details: les amis" });
    expect(screen.queryByRole("region", { name: "Details: Bonjour" })).not.toBeInTheDocument();
    expect(within(card).getByRole("list", { name: /sound by sound/i })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: /hear the model/i })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: /hear yourself/i })).toBeInTheDocument();
    expect(within(card).getByText("The whole word is correct")).toBeInTheDocument();
    expect(within(card).queryByRole("heading", { name: "Needs fixing" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^les amis/ }));
    expect(screen.queryByRole("region", { name: /^Details:/ })).not.toBeInTheDocument();
  });

  it("puts 'Needs fixing' before 'Already good' inside a card", () => {
    renderResults(attempt([BONJOUR, LES_AMIS]));
    const card = screen.getByRole("region", { name: "Details: Bonjour" });
    const headings = within(card).getAllByRole("heading").map((h) => h.textContent);
    expect(headings).toEqual(["Needs fixing", "Already good"]);
    expect(within(card).getByText(/Correct:/)).toHaveTextContent("Correct: /b/");
  });

  it("the model clip is the reference audio of that word", () => {
    renderResults(attempt([BONJOUR, LES_AMIS]));
    expect(within(screen.getByRole("region", { name: "Details: Bonjour" })).getByRole("button", { name: /hear the model/i })).toBeInTheDocument();
  });

  it("groups the chips by chunk for a whole-sentence attempt", () => {
    renderResults(attempt([BONJOUR, LES_AMIS], true));
    expect(screen.getByRole("group", { name: "Chunk 1: Bonjour" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Chunk 2: les amis" })).toBeInTheDocument();
  });

  it("has no numeric score anywhere", () => {
    renderResults(attempt([BONJOUR, LES_AMIS]));
    expect(screen.queryByText(/\d+\s*\/\s*100/)).not.toBeInTheDocument();
  });

  it("keeps the limitation hints inside the card", () => {
    renderResults(attempt([unitResult("c0_unit_0", [op("match", "b", "b"), op("insertion", null, "t")]), LES_AMIS]));
    expect(screen.getByText(/links this word to the next chunk/i)).toBeInTheDocument();
  });
});
