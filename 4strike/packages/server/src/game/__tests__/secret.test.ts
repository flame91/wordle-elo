import { describe, expect, it } from "vitest";
import { formatSecret, generateSecret, isValidSecret, parseSecret } from "../secret.js";

describe("isValidSecret", () => {
  it("accepts valid 4-digit secret with unique digits in 1..6", () => {
    expect(isValidSecret([1, 2, 3, 4])).toBe(true);
    expect(isValidSecret([6, 5, 4, 3])).toBe(true);
  });

  it("rejects wrong length", () => {
    expect(isValidSecret([1, 2, 3])).toBe(false);
    expect(isValidSecret([1, 2, 3, 4, 5])).toBe(false);
  });

  it("rejects out-of-range digits", () => {
    expect(isValidSecret([0, 1, 2, 3])).toBe(false);
    expect(isValidSecret([1, 2, 3, 7])).toBe(false);
  });

  it("rejects duplicate digits", () => {
    expect(isValidSecret([1, 1, 2, 3])).toBe(false);
    expect(isValidSecret([1, 2, 3, 2])).toBe(false);
  });

  it("rejects non-integer or non-number entries", () => {
    expect(isValidSecret([1.5, 2, 3, 4])).toBe(false);
    expect(isValidSecret(["1", 2, 3, 4])).toBe(false);
  });
});

describe("generateSecret", () => {
  it("produces 4 unique digits in 1..6", () => {
    for (let i = 0; i < 200; i++) {
      const s = generateSecret();
      expect(isValidSecret(s)).toBe(true);
    }
  });

  it("uses the provided rng deterministically", () => {
    const seq = [0, 0, 0, 0];
    let i = 0;
    const rng = () => {
      const v = seq[i] ?? 0;
      i++;
      return v;
    };
    expect(generateSecret(rng)).toEqual([1, 2, 3, 4]);
  });
});

describe("parseSecret", () => {
  it("parses well-formed input", () => {
    expect(parseSecret("1234")).toEqual([1, 2, 3, 4]);
  });

  it("rejects malformed input", () => {
    expect(parseSecret("12")).toBeNull();
    expect(parseSecret("1224")).toBeNull();
    expect(parseSecret("12a4")).toBeNull();
    expect(parseSecret("1278")).toBeNull();
  });
});

describe("formatSecret", () => {
  it("joins digits into a string", () => {
    expect(formatSecret([1, 2, 3, 4] as never)).toBe("1234");
  });
});
