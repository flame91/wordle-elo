import type { SBResult, SecretCode } from "./types.js";

export function calculateSB(secret: SecretCode, guess: SecretCode): SBResult {
  let strikes = 0;
  let balls = 0;
  for (let i = 0; i < secret.length; i++) {
    const g = guess[i];
    if (g === secret[i]) {
      strikes++;
    } else if (g !== undefined && secret.includes(g)) {
      balls++;
    }
  }
  return { strikes, balls };
}

export function isFourStrike(result: SBResult): boolean {
  return result.strikes === 4;
}
