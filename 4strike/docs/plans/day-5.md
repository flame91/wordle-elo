# Day 5 — JSONL 영속화 + Cloudflare Tunnel

## 목표

종료 매치 JSONL append + 외부 접속 가능한 영구 터널 + 헬스체크.

## 산출물

- `packages/server/src/persistence/jsonl.ts` — `appendMatch(record)`
  - 1라인 1매치: `{matchId, startedAt, finishedAt, totalRounds, endReason, players, winnerId, guildId}`
  - `data/matches-YYYY-MM.jsonl` 월별 롤링
  - `fs.appendFileSync` (단일 프로세스 가정)
- `session/manager.ts`의 `onGameOver → appendMatch()` 콜백
- Cloudflare Tunnel **named tunnel** 영구 설정 (`cloudflared` config 파일)
- `GET /health` 엔드포인트 (`200 ok`)
- healthcheck.io 5분 ping (다운 5분 후 폰 알림)

## 검증

- 터널 URL 외부 접속
- 1판 종료 후 `data/matches-*.jsonl`에 row 1줄, `jq` 파싱 OK
- 서버 다운 시 healthcheck.io 알림 동작
