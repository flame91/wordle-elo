# Day 1 — 부트스트랩 + 게임 로직

## 목표

pnpm workspace 셋업 + `packages/server/src/game/` 순수 로직 + Vitest 핵심 테스트 그린.

## 산출물

- root: `package.json`, `pnpm-workspace.yaml`, `tsconfig.base.json`, `vitest.config.ts`, `.gitignore`, `.env.example`, `.prettierrc`, `.github/workflows/ci.yml`
- workspaces: `packages/{shared,server,client}/package.json`, `tsconfig.json`
- `packages/server/src/game/`:
  - `types.ts` — `Player`, `Guess`, `RoundResult`, `GameState`, `EndReason`
  - `secret.ts` — `generateSecret()`, `isValidSecret(code)` (1-6, 4자리, 중복없음)
  - `score.ts` — `calculateSB(secret, guess): { strikes, balls }`
  - `clock.ts` — DI용 라운드/인터미션 시간 상수
  - `state.ts` — 라운드제 state machine
- `packages/server/src/game/__tests__/score.test.ts`, `secret.test.ts`, `state.test.ts`
- `docs/plans/` skeleton

## 검증

- `pnpm install` 성공
- `pnpm typecheck` 그린
- `pnpm test` 그린 (최소 8 케이스)
