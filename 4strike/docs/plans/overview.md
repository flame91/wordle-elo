# 4Strike Simple MVP — Overview

1주 / 5-10명 클로즈드 베타 / JSONL 영속화. Discord Activity로 친구 풀에 노출되는 최소 슬라이스.

마스터 플랜은 세션 컨텍스트(`/root/.claude/plans/optimized-giggling-parnas.md`) 참고. 이 파일은 repo 안 영구 사본의 진입점.

## 라운드 구조

- 60s / 라운드 × 최대 6라운드 + 라운드 사이 10s 인터미션 → 매치 캡 ≈ 7분
- 양 플레이어 동시 비공개 입력 → 동시 공개 (`ROUND_REVEAL`)
- 종료 조건: 4S 단독 / 6라운드 소진(strikes 합 → balls 합 → draw) / 동시 4S=draw / 누적 패스 자동 패배

## 매칭

- **글로벌 단일 FIFO 큐**. guild_id는 매칭 키 아님 (메타데이터로만 매치 로그에 기록).
- Discord 역할: 인증 / Activity 런처 / 결과 알림.

## 타임아웃 자동 동작 (클라이언트)

- 유효한 4자리(중복없는 1-6): 자동 `SUBMIT_GUESS` 송신
- 미완성 / 빈 입력: 송신 생략 → 서버가 패스로 처리

## 일정

| Day | 주제 | 산출물 |
| --- | --- | --- |
| 1 | 부트스트랩 + 게임 로직 | workspace, `packages/server/src/game/*`, score 테스트 |
| 2 | 서버 (Fastify + WS) | shared protocol, 글로벌 큐, 라운드 진행 매니저 |
| 3 | 클라이언트 (Vite + React) | 4 화면, ws/client, 타임아웃 자동 동작 |
| 4 | Discord Activity 통합 | Embedded SDK + access_token 검증 |
| 5 | JSONL 영속화 + Cloudflare Tunnel | append-only 로그, named tunnel, /health |
| 6 | 폴리시 | reconnect, 누적 패스 자동패배, error boundary |
| 7 | 친구 베타 + 버그픽스 | 베타 진행, jq 분석 |

## Acceptance

- 친구 2명 이상이 실제 Discord Activity에서 매칭 → 6라운드 → 정상 종료
- `data/matches-*.jsonl`에 매치 row 누적, jq 분석 가능
- 베타 5-10판 누적, 크래시 0
