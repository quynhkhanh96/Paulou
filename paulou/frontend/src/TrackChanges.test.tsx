import { render, screen, within } from "@testing-library/react";
import { op } from "./fixtures";
import { TrackChanges } from "./TrackChanges";

describe("TrackChanges", () => {
  it("gives every kind its own class and an accessible description", () => {
    render(
      <TrackChanges
        ops={[
          op("match", "l", "l"),
          op("substitution", "ɔ̃", "o", "S_near", ["missing_nasality", "not_open_enough"]),
          op("substitution", "ʁ", "l"),
          op("deletion", "z", null),
          op("insertion", null, "t"),
        ]}
      />,
    );
    const items = within(screen.getByRole("list", { name: /sound by sound/i })).getAllByRole("listitem");
    expect(items.map((li) => li.className)).toEqual(["tk tk-M", "tk tk-S_near", "tk tk-S", "tk tk-D", "tk tk-I"]);
    expect(items.map((li) => li.getAttribute("aria-label"))).toEqual([
      "l: correct",
      "ɔ̃: close, heard o, missing nasality, mouth not open enough",
      "ʁ: heard l instead",
      "z: missing",
      "t: extra sound",
    ]);
  });

  it("shows the heard sound above a substitution, and nothing above a match", () => {
    const { container } = render(<TrackChanges ops={[op("match", "a", "a"), op("substitution", "z", "s", "S_near", ["missing_voicing"])]} />);
    const tops = [...container.querySelectorAll(".tk-top")].map((e) => e.textContent);
    expect(tops).toEqual(["", "s"]);
  });

  it("merges consecutive extra sounds under one caret", () => {
    const { container } = render(
      <TrackChanges ops={[op("match", "a", "a"), op("insertion", null, "t"), op("insertion", null, "s"), op("match", "b", "b")]} />,
    );
    expect(container.querySelectorAll(".tk-I")).toHaveLength(1);
    expect(container.querySelector(".tk-I .tk-top")?.textContent).toBe("+t s");
    expect(container.querySelector(".tk-I .tk-main")?.textContent).toBe("‸");
  });

  it("puts an extra sound between the two sounds it sits between", () => {
    const { container } = render(<TrackChanges ops={[op("match", "a", "a"), op("insertion", null, "t"), op("match", "b", "b")]} />);
    expect([...container.querySelectorAll("li")].map((li) => li.className)).toEqual(["tk tk-M", "tk tk-I", "tk tk-M"]);
  });
});
