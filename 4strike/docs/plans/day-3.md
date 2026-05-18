# Day 3 — 클라이언트 (Vite + React + Tailwind + Zustand)

## 목표

두 브라우저 탭으로 한 판 플레이 가능 (Discord 미통합).

## 산출물

- `packages/client/`:
  - Vite + React 18 + Tailwind + Zustand
  - `src/main.tsx`, `App.tsx`, `index.html`
  - `src/store.ts` — Zustand (게임 상태, WS 연결, 현재 라운드)
  - `src/ws/client.ts` — shared protocol import
  - `src/screens/{Lobby,SecretEntry,Game,Result}.tsx`
- **타임아웃 자동 동작**:
  - 60s 종료 시점에 입력이 유효 4자리(중복없는 1-6)면 자동 `SUBMIT_GUESS`
  - 미완성/빈 입력이면 송신 생략 → 서버가 패스로 처리
- UI: 라운드 인디케이터("Round 3 / 6"), 60s + 10s 카운트다운, 양쪽 라운드별 히스토리

## 검증

- `pnpm --filter @4strike/server dev` + `pnpm --filter @4strike/client dev`
- 두 브라우저 탭으로 한 판
