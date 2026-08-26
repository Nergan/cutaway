import { describe, it, expect } from "vitest";
import { isWithinSlidingWindow } from "../src/domain/time_policy.js";

describe("isWithinSlidingWindow", () => {
  it("accepts exact match", () => {
    expect(isWithinSlidingWindow(1000, 1000)).toBe(true);
  });

  it("accepts values within ±30s", () => {
    expect(isWithinSlidingWindow(1000, 1029)).toBe(true);
    expect(isWithinSlidingWindow(1000, 971)).toBe(true);
  });

  it("accepts exactly at the boundary (30s)", () => {
    expect(isWithinSlidingWindow(1000, 1030)).toBe(true);
    expect(isWithinSlidingWindow(1000, 970)).toBe(true);
  });

  it("rejects values just outside the boundary", () => {
    expect(isWithinSlidingWindow(1000, 1031)).toBe(false);
    expect(isWithinSlidingWindow(1000, 969)).toBe(false);
  });

  it("respects a custom window", () => {
    expect(isWithinSlidingWindow(1000, 1100, 200)).toBe(true);
    expect(isWithinSlidingWindow(1000, 1300, 200)).toBe(false);
  });
});
