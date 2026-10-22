import { render, screen, within } from "@testing-library/react";
import { op } from "./fixtures";
import { Legend, PhonemeStrip, describeOp } from "./PhonemeStrip";

describe("PhonemeStrip", () => {
  const ops = [op("match", "l", "l"), op("deletion", "z", null), op("substitution", "a", "ɑ"), op("insertion", null, "t")];

  it("renders one item per op in the given order", () => {
    render(<PhonemeStrip ops={ops} />);
    const items = within(screen.getByRole("list", { name: /sound by sound/i })).getAllByRole("listitem");
    expect(items.map((li) => li.getAttribute("aria-label"))).toEqual([
      "l: said correctly",
      "z: missing",
      "a: heard ɑ instead",
      "t: extra sound",
    ]);
  });

  it("does not rely on colour alone: every type has its own visible marker", () => {
    const { container } = render(<PhonemeStrip ops={ops} />);
    const glyphs = [...container.querySelectorAll(".phone-glyph")].map((g) => g.textContent);
    expect(glyphs).toEqual(["✓", "–", "≠", "+"]);
    expect(container.querySelector(".substitution")).toHaveTextContent("heard ɑ");
    expect(container.querySelector(".deletion")).toHaveTextContent("missing");
    expect(container.querySelector(".insertion")).toHaveTextContent("extra");
  });

  it("shows the decoded sound for an insertion and the canonical one otherwise", () => {
    const { container } = render(<PhonemeStrip ops={[op("insertion", null, "t"), op("deletion", "ə", null)]} />);
    const sounds = [...container.querySelectorAll(".phone-sound")].map((s) => s.textContent);
    expect(sounds).toEqual(["t", "ə"]);
  });

  it("describeOp covers all four types", () => {
    expect(describeOp(op("match", "a", "a"))).toBe("a: said correctly");
  });

  it("legend names all four outcomes", () => {
    render(<Legend />);
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
  });
});
