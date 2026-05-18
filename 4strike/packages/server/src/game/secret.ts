import { DIGIT_MAX, DIGIT_MIN, SECRET_LENGTH, type Digit, type SecretCode } from "./types.js";

const digits: readonly Digit[] = [1, 2, 3, 4, 5, 6];

export function generateSecret(rng: () => number = Math.random): SecretCode {
  const pool: Digit[] = digits.slice();
  const out: Digit[] = [];
  for (let i = 0; i < SECRET_LENGTH; i++) {
    const idx = Math.floor(rng() * pool.length);
    const picked = pool.splice(idx, 1)[0];
    if (picked === undefined) throw new Error("rng produced invalid index");
    out.push(picked);
  }
  return out as unknown as SecretCode;
}

export function isValidSecret(code: readonly unknown[]): code is SecretCode {
  if (code.length !== SECRET_LENGTH) return false;
  const seen = new Set<number>();
  for (const d of code) {
    if (typeof d !== "number") return false;
    if (!Number.isInteger(d)) return false;
    if (d < DIGIT_MIN || d > DIGIT_MAX) return false;
    if (seen.has(d)) return false;
    seen.add(d);
  }
  return true;
}

export function parseSecret(input: string): SecretCode | null {
  if (input.length !== SECRET_LENGTH) return null;
  const arr: number[] = [];
  for (const ch of input) {
    const n = Number(ch);
    if (Number.isNaN(n)) return null;
    arr.push(n);
  }
  return isValidSecret(arr) ? (arr as unknown as SecretCode) : null;
}

export function formatSecret(code: SecretCode): string {
  return code.join("");
}
