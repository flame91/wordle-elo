import { describe, expect, it } from "vitest";
import { calculateSB, isFourStrike } from "../score.js";
import type { SecretCode } from "../types.js";

const code = (a: number, b: number, c: number, d: number): SecretCode =>
  [a, b, c, d] as unknown as SecretCode;

describe("calculateSB", () => {
  it("returns 4 strikes for exact match", () => {
    expect(calculateSB(code(1, 2, 3, 4), code(1, 2, 3, 4))).toEqual({ strikes: 4, balls: 0 });
  });

  it("returns 0 strikes 0 balls for fully disjoint", () => {
    expect(calculateSB(code(1, 2, 3, 4), code(5, 6, 5, 6))).toEqual({ strikes: 0, balls: 0 });
  });

  it("returns 0 strikes 4 balls for a full reverse permutation", () => {
    expect(calculateSB(code(1, 2, 3, 4), code(4, 3, 2, 1))).toEqual({ strikes: 0, balls: 4 });
  });

  it("returns 2 strikes 2 balls for partial position match plus swap", () => {
    expect(calculateSB(code(1, 2, 3, 4), code(1, 2, 4, 3))).toEqual({ strikes: 2, balls: 2 });
  });

  it("returns 1 strike for a single-position match with no overlap", () => {
    expect(calculateSB(code(1, 2, 3, 4), code(1, 5, 6, 5))).toEqual({ strikes: 1, balls: 0 });
  });

  it("returns 3 strikes 0 balls when last digit differs and is not in secret", () => {
    expect(calculateSB(code(1, 2, 3, 4), code(1, 2, 3, 5))).toEqual({ strikes: 3, balls: 0 });
  });

  it("counts a misplaced digit not in secret as nothing", () => {
    expect(calculateSB(code(1, 2, 3, 4), code(5, 5, 5, 5))).toEqual({ strikes: 0, balls: 0 });
  });

  it("isFourStrike detects winning result", () => {
    expect(isFourStrike({ strikes: 4, balls: 0 })).toBe(true);
    expect(isFourStrike({ strikes: 3, balls: 1 })).toBe(false);
  });
});
