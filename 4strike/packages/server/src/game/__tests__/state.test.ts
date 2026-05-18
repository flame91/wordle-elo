import { describe, expect, it } from "vitest";
import {
  advanceToNextRound,
  createMatchState,
  MAX_CONSECUTIVE_PASSES,
  resolveRound,
  setSecret,
} from "../state.js";
import type { GameState, SecretCode } from "../types.js";

const code = (a: number, b: number, c: number, d: number): SecretCode =>
  [a, b, c, d] as unknown as SecretCode;

function freshMatchWithSecrets(secretA: SecretCode, secretB: SecretCode): GameState {
  let s = createMatchState("m1", "alice", "bob");
  s = setSecret(s, "alice", secretA);
  s = setSecret(s, "bob", secretB);
  return s;
}

describe("createMatchState", () => {
  it("starts in SECRETS_PENDING with zeroed counters", () => {
    const s = createMatchState("m1", "alice", "bob");
    expect(s.phase).toBe("SECRETS_PENDING");
    expect(s.currentRound).toBe(0);
    expect(s.rounds).toEqual([]);
    expect(s.consecutivePasses).toEqual({ alice: 0, bob: 0 });
  });

  it("rejects same id for both players", () => {
    expect(() => createMatchState("m1", "alice", "alice")).toThrow();
  });
});

describe("setSecret", () => {
  it("transitions to ROUND_INPUT once both secrets are set", () => {
    let s = createMatchState("m1", "alice", "bob");
    s = setSecret(s, "alice", code(1, 2, 3, 4));
    expect(s.phase).toBe("SECRETS_PENDING");
    s = setSecret(s, "bob", code(5, 6, 1, 2));
    expect(s.phase).toBe("ROUND_INPUT");
  });

  it("rejects an unknown player", () => {
    const s = createMatchState("m1", "alice", "bob");
    expect(() => setSecret(s, "charlie", code(1, 2, 3, 4))).toThrow();
  });
});

describe("resolveRound — terminal cases", () => {
  it("ends with a win when one player hits 4S", () => {
    const s = freshMatchWithSecrets(code(1, 2, 3, 4), code(4, 3, 2, 1));
    const next = resolveRound(
      s,
      { alice: code(4, 3, 2, 1), bob: code(5, 6, 1, 2) },
      1000,
    );
    expect(next.phase).toBe("FINISHED");
    expect(next.endReason).toBe("win");
    expect(next.winnerId).toBe("alice");
  });

  it("ends as a draw when both hit 4S in the same round", () => {
    const s = freshMatchWithSecrets(code(1, 2, 3, 4), code(4, 3, 2, 1));
    const next = resolveRound(
      s,
      { alice: code(4, 3, 2, 1), bob: code(1, 2, 3, 4) },
      1000,
    );
    expect(next.phase).toBe("FINISHED");
    expect(next.endReason).toBe("draw");
    expect(next.winnerId).toBeNull();
  });

  it("returns ROUND_REVEAL phase mid-match and advances to ROUND_INPUT", () => {
    const s = freshMatchWithSecrets(code(1, 2, 3, 4), code(5, 6, 1, 2));
    const after1 = resolveRound(
      s,
      { alice: code(2, 1, 4, 3), bob: code(4, 3, 2, 1) },
      1000,
    );
    expect(after1.phase).toBe("ROUND_REVEAL");
    expect(after1.currentRound).toBe(1);
    expect(advanceToNextRound(after1).phase).toBe("ROUND_INPUT");
  });
});

describe("resolveRound — pass accumulation", () => {
  it("force-loses a player who passes three rounds in a row", () => {
    let s = freshMatchWithSecrets(code(1, 2, 3, 4), code(5, 6, 1, 2));
    for (let i = 0; i < MAX_CONSECUTIVE_PASSES - 1; i++) {
      s = resolveRound(s, { alice: null, bob: code(4, 3, 2, 1) }, 1000 + i);
      s = advanceToNextRound(s);
    }
    const final = resolveRound(s, { alice: null, bob: code(4, 3, 2, 1) }, 9999);
    expect(final.phase).toBe("FINISHED");
    expect(final.endReason).toBe("timeout");
    expect(final.winnerId).toBe("bob");
  });
});

describe("resolveRound — rounds exhausted", () => {
  it("awards the win to the higher accumulated strike total after 6 rounds", () => {
    let s = freshMatchWithSecrets(code(1, 2, 3, 4), code(5, 6, 1, 2));
    // alice guesses with 1 strike each round (1234 → not 5612, just 1 ball typically; pick a careful guess)
    // Bob's secret is 5,6,1,2 → alice guessing 5,2,3,4 lands 1 strike (position 0) + ball for 2.
    // We use guesses that never reach 4S to force rounds_exhausted.
    const aliceGuess = code(5, 2, 3, 4); // vs secretB 5612 → strike on 5, ball on 2 → S=1 B=1
    const bobGuess = code(1, 3, 4, 5); // vs secretA 1234 → strike on 1, ball on 3,4 → S=1 B=2
    for (let r = 0; r < 6; r++) {
      s = resolveRound(s, { alice: aliceGuess, bob: bobGuess }, 1000 + r);
      if (s.phase === "ROUND_REVEAL") s = advanceToNextRound(s);
    }
    expect(s.phase).toBe("FINISHED");
    expect(s.endReason).toBe("rounds_exhausted");
    // Bob accumulates more balls (2 vs 1) per round, tiebreak after strikes equal.
    expect(s.winnerId).toBe("bob");
  });

  it("results in a draw when both totals are identical after 6 rounds", () => {
    let s = freshMatchWithSecrets(code(1, 2, 3, 4), code(4, 3, 2, 1));
    // Symmetric: each guesses the other's exact secret would be a 4S immediately,
    // so use a mutually weak guess that yields S=0 B=4 both ways every round.
    const aliceGuess = code(1, 2, 3, 4); // vs secretB 4321 → all wrong positions, 4 balls
    const bobGuess = code(4, 3, 2, 1); // vs secretA 1234 → all wrong positions, 4 balls
    for (let r = 0; r < 6; r++) {
      s = resolveRound(s, { alice: aliceGuess, bob: bobGuess }, 1000 + r);
      if (s.phase === "ROUND_REVEAL") s = advanceToNextRound(s);
    }
    expect(s.phase).toBe("FINISHED");
    expect(s.endReason).toBe("draw");
    expect(s.winnerId).toBeNull();
  });
});
