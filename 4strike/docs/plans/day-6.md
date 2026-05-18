# Day 6 — 폴리시

## 목표

엣지 케이스 처리 + 어뷰즈 방지 + UI 마감.

## 산출물

- Disconnect/reconnect: 클라 WS 자동 재연결 5s grace → 실패 시 서버가 `abandon` 종료
- 누적 패스 자동 패배: 3연속 패스 또는 통산 4패스 → `end_reason=timeout`
- 6라운드 소진 종료 규칙: strikes 합 → balls 합 → draw
- 동시 4S → draw
- React error boundary + 사용자 친화 에러 UI
- 임시 파비콘/로고

## 검증

- 의도적 끊기 케이스 테스트 (탭 닫기, 네트워크 차단 후 복귀)
- 타임아웃/패스 시나리오 3종 수동
- 동시 4S 무승부 케이스
