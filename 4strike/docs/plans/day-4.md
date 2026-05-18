# Day 4 — Discord Activity 통합

## 목표

Discord Developer Portal 셋업 + Embedded App SDK + 서버 측 토큰 검증.

## 산출물

- Discord Developer Portal: Application + Activity 생성 (Activity URL은 Day 5 터널 URL)
- `packages/client/src/discord/sdk.ts` — `@discord/embedded-app-sdk` 초기화 + `authenticate()` flow
- WS 첫 메시지에 Discord `access_token` 포함 → 서버 `auth/discord.ts`에서 `https://discord.com/api/users/@me` 검증 → 내부 `userId = discord_id`
- guild_id 추출 → 매치 시작 시 메타데이터 캐시 (매칭 키 아님)

## 검증

- 본인 Discord 서버에서 Activity 실행 (두 계정 또는 두 탭으로 1판)
