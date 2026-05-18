import { calculateSB, isFourStrike } from "./score.js";
import { isValidSecret } from "./secret.js";
import {
  MAX_ROUNDS,
  type EndReason,
  type GameState,
  type Guess,
  type RoundResult,
  type SBResult,
  type SecretCode,
} from "./types.js";

export const MAX_CONSECUTIVE_PASSES = 3;
export const MAX_TOTAL_PASSES = 4;

export interface RoundInputs {
  readonly [playerId: string]: SecretCode | null | undefined;
}

export function createMatchState(matchId: string, playerA: string, playerB: string): GameState {
  if (playerA === playerB) throw new Error("playerA and playerB must differ");
  return {
    matchId,
    phase: "SECRETS_PENDING",
    playerA,
    playerB,
    secrets: {},
    currentRound: 0,
    rounds: [],
    consecutivePasses: { [playerA]: 0, [playerB]: 0 },
    totalPasses: { [playerA]: 0, [playerB]: 0 },
  };
}

export function setSecret(state: GameState, playerId: string, code: SecretCode): GameState {
  if (state.phase !== "SECRETS_PENDING") {
    throw new Error(`cannot set secret in phase ${state.phase}`);
  }
  if (playerId !== state.playerA && playerId !== state.playerB) {
    throw new Error("unknown player");
  }
  if (!isValidSecret(code)) {
    throw new Error("invalid secret");
  }
  const secrets = { ...state.secrets, [playerId]: code };
  const both = secrets[state.playerA] && secrets[state.playerB];
  return {
    ...state,
    secrets,
    phase: both ? "ROUND_INPUT" : "SECRETS_PENDING",
  };
}

/**
 * Resolve a single round given each player's submitted guess (or null/undefined for pass).
 * Returns updated state including the recorded RoundResult and any terminal end_reason/winner.
 */
export function resolveRound(state: GameState, inputs: RoundInputs, now: number): GameState {
  if (state.phase !== "ROUND_INPUT") {
    throw new Error(`cannot resolve round in phase ${state.phase}`);
  }
  const secretA = state.secrets[state.playerA];
  const secretB = state.secrets[state.playerB];
  if (!secretA || !secretB) throw new Error("secrets not set");

  const guessA = normalizeInput(inputs[state.playerA]);
  const guessB = normalizeInput(inputs[state.playerB]);

  const resultAagainstB: SBResult = guessA ? calculateSB(secretB, guessA) : { strikes: 0, balls: 0 };
  const resultBagainstA: SBResult = guessB ? calculateSB(secretA, guessB) : { strikes: 0, balls: 0 };

  const round: RoundResult = {
    roundIndex: state.currentRound,
    guesses: [
      makeGuess(state.playerA, state.currentRound, guessA, resultAagainstB, now),
      makeGuess(state.playerB, state.currentRound, guessB, resultBagainstA, now),
    ],
  };

  const consecutivePasses = {
    ...state.consecutivePasses,
    [state.playerA]: guessA ? 0 : (state.consecutivePasses[state.playerA] ?? 0) + 1,
    [state.playerB]: guessB ? 0 : (state.consecutivePasses[state.playerB] ?? 0) + 1,
  };
  const totalPasses = {
    ...state.totalPasses,
    [state.playerA]: (state.totalPasses[state.playerA] ?? 0) + (guessA ? 0 : 1),
    [state.playerB]: (state.totalPasses[state.playerB] ?? 0) + (guessB ? 0 : 1),
  };

  const rounds = [...state.rounds, round];

  const terminal = decideTerminal({
    aHit: isFourStrike(resultAagainstB),
    bHit: isFourStrike(resultBagainstA),
    playerA: state.playerA,
    playerB: state.playerB,
    consecutivePasses,
    totalPasses,
    rounds,
  });

  if (terminal) {
    return {
      ...state,
      phase: "FINISHED",
      rounds,
      consecutivePasses,
      totalPasses,
      currentRound: state.currentRound + 1,
      endReason: terminal.reason,
      winnerId: terminal.winnerId,
    };
  }

  return {
    ...state,
    phase: "ROUND_REVEAL",
    rounds,
    consecutivePasses,
    totalPasses,
    currentRound: state.currentRound + 1,
  };
}

export function advanceToNextRound(state: GameState): GameState {
  if (state.phase !== "ROUND_REVEAL") {
    throw new Error(`cannot advance from phase ${state.phase}`);
  }
  return { ...state, phase: "ROUND_INPUT" };
}

interface TerminalDecisionArgs {
  readonly aHit: boolean;
  readonly bHit: boolean;
  readonly playerA: string;
  readonly playerB: string;
  readonly consecutivePasses: Record<string, number>;
  readonly totalPasses: Record<string, number>;
  readonly rounds: readonly RoundResult[];
}

interface TerminalDecision {
  readonly reason: EndReason;
  readonly winnerId: string | null;
}

function decideTerminal(args: TerminalDecisionArgs): TerminalDecision | null {
  const { aHit, bHit, playerA, playerB, consecutivePasses, totalPasses, rounds } = args;

  if (aHit && bHit) return { reason: "draw", winnerId: null };
  if (aHit) return { reason: "win", winnerId: playerA };
  if (bHit) return { reason: "win", winnerId: playerB };

  const aTimedOut = isTimeoutLoss(consecutivePasses[playerA] ?? 0, totalPasses[playerA] ?? 0);
  const bTimedOut = isTimeoutLoss(consecutivePasses[playerB] ?? 0, totalPasses[playerB] ?? 0);
  if (aTimedOut && bTimedOut) return { reason: "draw", winnerId: null };
  if (aTimedOut) return { reason: "timeout", winnerId: playerB };
  if (bTimedOut) return { reason: "timeout", winnerId: playerA };

  if (rounds.length >= MAX_ROUNDS) {
    return decideByAccumulated(rounds, playerA, playerB);
  }

  return null;
}

function isTimeoutLoss(consecutive: number, total: number): boolean {
  return consecutive >= MAX_CONSECUTIVE_PASSES || total >= MAX_TOTAL_PASSES;
}

function decideByAccumulated(
  rounds: readonly RoundResult[],
  playerA: string,
  playerB: string,
): TerminalDecision {
  let aStrikes = 0;
  let bStrikes = 0;
  let aBalls = 0;
  let bBalls = 0;
  for (const round of rounds) {
    for (const g of round.guesses) {
      if (g.playerId === playerA) {
        aStrikes += g.result.strikes;
        aBalls += g.result.balls;
      } else if (g.playerId === playerB) {
        bStrikes += g.result.strikes;
        bBalls += g.result.balls;
      }
    }
  }
  if (aStrikes !== bStrikes) {
    return { reason: "rounds_exhausted", winnerId: aStrikes > bStrikes ? playerA : playerB };
  }
  if (aBalls !== bBalls) {
    return { reason: "rounds_exhausted", winnerId: aBalls > bBalls ? playerA : playerB };
  }
  return { reason: "draw", winnerId: null };
}

function normalizeInput(value: SecretCode | null | undefined): SecretCode | null {
  if (!value) return null;
  return isValidSecret(value) ? value : null;
}

function makeGuess(
  playerId: string,
  roundIndex: number,
  code: SecretCode | null,
  result: SBResult,
  submittedAt: number,
): Guess {
  return {
    playerId,
    roundIndex,
    code,
    isPass: code === null,
    result,
    submittedAt,
  };
}
