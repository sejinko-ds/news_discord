# news_discord

RSS와 API에서 뉴스를 수집해 Discord로 전송하는 봇

## 인프라

**Cloudflare Workers** (Python) + **D1** (SQLite)

- 배포: GitHub 연동 (`sejinko-ds/news_discord` → Cloudflare Git Integration)
- 스케줄: Cron Trigger (`*/30`) + 코드 내 KST 시간 필터
- DB: Cloudflare D1 (`discord-news-db`) - 중복 발송 방지

## 스케줄

- 월~금, 06:00~18:00 KST, 30분 간격
- 30일 이상 된 기록 자동 삭제

## 뉴스 소스

| 소스 | 방식 | URL |
|------|------|-----|
| GeekNews (Hada) | RSS (Atom) | `https://news.hada.io/rss/news` |
| AI Times | RSS | `https://www.aitimes.com/rss/allArticle.xml` |
| Yozm Wishket AI | JSON API | `https://api.wishket.com/yozmit/news/?category=ai` |

- 소스별 최대 30개 기사 확인
- URL 해시(SHA-256)로 중복 체크

## 주요 파일

| 파일 | 설명 |
|------|------|
| `src/entry.py` | Cloudflare Worker 메인 코드 |
| `wrangler.toml` | Cloudflare Workers 설정 |
| `pyproject.toml` | Python 의존성 |
| `schema.sql` | D1 테이블 스키마 (참고용, 코드에서 자동 생성) |

## 환경 변수 (Cloudflare Secrets)

- `DISCORD_WEBHOOK_URL`: Discord 웹훅 URL (`npx wrangler secret put` 으로 설정)
