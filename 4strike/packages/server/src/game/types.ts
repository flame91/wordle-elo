export const DIGIT_MIN = 1;
export const DIGIT_MAX = 6;
export const SECRET_LENGTH = 4;
export const MAX_ROUNDS = 6;

export type Digit = 1 | 2 | 3 | 4 | 5 | 6;
export type SecretCode = readonly [Digit, Digit, Digit, Digit];

export interface PlayerId {
  readonly id: string;
}

export interface SBResult {
  readonly strikes: number;
  readonly balls: number;
}

export interface Guess {
  readonly playerId: string;
  readonly roundIndex: number;
  readonly code: SecretCode | null;
  readonly isPass: boolean;
  readonly result: SBResult;
  readonly submittedAt: number;
}

export interface RoundResult {
  readonly roundIndex: number;
  readonly guesses: readonly Guess[];
}

export type GamePhase =
  | "LOBBY"
  | "SECRETS_PENDING"
  | "ROUND_INPUT"
  | "ROUND_REVEAL"
  | "FINISHED";

export type EndReason = "win" | "timeout" | "abandon" | "rounds_exhausted" | "draw";

export interface GameState {
  readonly matchId: string;
  readonly phase: GamePhase;
  readonly playerA: string;
  readonly playerB: string;
  readonly secrets: Record<string, SecretCode | undefined>;
  readonly currentRound: number;
  readonly rounds: readonly RoundResult[];
  readonly consecutivePasses: Record<string, number>;
  readonly totalPasses: Record<string, number>;
  readonly endReason?: EndReason;
  readonly winnerId?: string | null;
}
