import { describe, expect, it } from "vitest";
import { Machine } from "./machine";

describe("Machine", () => {
  it("starts idle and follows the happy path", () => {
    const m = new Machine();
    expect(m.state).toBe("idle");
    for (const s of ["permission", "reading", "processing", "hello",
                     "briefing", "generating", "reveal", "feedback", "gallery"] as const) {
      m.go(s);
      expect(m.state).toBe(s);
    }
  });

  it("allows thumbs-down regeneration loop", () => {
    const m = new Machine();
    m.go("permission"); m.go("reading"); m.go("processing"); m.go("hello");
    m.go("briefing"); m.go("generating"); m.go("reveal"); m.go("feedback");
    m.go("generating");
    expect(m.state).toBe("generating");
  });

  it("throws on illegal transition", () => {
    const m = new Machine();
    expect(() => m.go("reveal")).toThrow(/illegal transition/);
  });

  it("notifies listeners on change", () => {
    const m = new Machine();
    const seen: string[] = [];
    m.onChange((s) => seen.push(s));
    m.go("permission");
    expect(seen).toEqual(["permission"]);
  });
});
