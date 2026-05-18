# Day 2 — 서버 (Fastify + WebSocket + 글로벌 큐 + 라운드 진행)

## 목표

DB·Discord 없이 인메모리만으로 매칭→플레이→종료까지 동작.

## 산출물

- `packages/shared/src/protocol.ts` — zod 메시지 스키마 (양방향 validation)
  - 메시지: `MATCHMAKE`, `MATCH_FOUND`, `SUBMIT_SECRET`, `SUBMIT_GUESS`, `ROUND_START`, `ROUND_RESULT`, `GAME_OVER`, `ERROR`, `PING`, `PONG`
- `packages/server/src/`:
  - `app.ts` — Fastify + `@fastify/websocket` 등록
  - `ws/router.ts` — 메시지 디스패치
  - `matchmaking/queue.ts` — **글로벌 단일 FIFO 큐** `Player[]`
  - `session/manager.ts` — 라운드 60s + 인터미션 10s 타이머. 라운드 종료 시 양쪽 추측 수집(미수신=패스) → S/B 계산 → `ROUND_RESULT` 동시 브로드캐스트 → 종료 판정
  - `index.ts` — 부트스트랩

## 검증

- `wscat` 2개로 매칭→코드 입력→6라운드 진행
- 시나리오 3종: 4S 승리 / 라운드 소진 (strikes 합 비교) / 패스 누적 자동 패배
