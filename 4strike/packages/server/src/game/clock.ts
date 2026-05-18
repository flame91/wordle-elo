export const ROUND_INPUT_MS = 60_000;
export const ROUND_INTERMISSION_MS = 10_000;
export const MATCH_HARD_CAP_MS = ROUND_INPUT_MS * 6 + ROUND_INTERMISSION_MS * 5;

export interface Clock {
  now(): number;
  setTimer(handler: () => void, ms: number): TimerHandle;
}

export interface TimerHandle {
  cancel(): void;
}

export const systemClock: Clock = {
  now: () => Date.now(),
  setTimer: (handler, ms) => {
    const id = setTimeout(handler, ms);
    return { cancel: () => clearTimeout(id) };
  },
};
