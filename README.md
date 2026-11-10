# 글로벌툰 (Global Toon) — 시사 웹툰 인스타그램 자동화

매일 3회, 국내·세계 핫이슈를 골라 **최대 6장 개그 웹툰 캐러셀**(표지 + 본문 4컷 + 3줄 요약)로 만들어 인스타그램에 자동 게시합니다.
**운영비 0원**(모두 무료 티어) / 실행은 **GitHub Actions**(PC 꺼져 있어도 동작).

```
[RSS 뉴스 수집] → [교차보도 검증·민감주제 제외] → [Gemini: 이슈 선정+대본] → [Gemini: 2차 팩트체크] → [Cloudflare FLUX: 컷 그림]
      → [Pillow: 한글 말풍선·해설·표지 합성] → [media 브랜치 업로드(공개 URL)] → [Instagram API 캐러셀 게시]
```

| 시간(KST) | 슬롯 | 주제 |
|---|---|---|
| 07:41 | morning | 국내 생활·경제 화제 |
| 12:13 | noon | 신기한 세계 소식 |
| 19:23 | evening | 테크·과학·문화·스포츠 |

### 기사 검증·논쟁 회피 4단계
1. **교차보도**: 서로 다른 언론사 3곳 이상이 보도한 이슈만 후보 (`news.min_sources`)
2. **민감 키워드 필터**: 정치·사건사고·소송·전쟁·갈등·의혹·단독 등 포함 시 자동 제외 (`safety.avoid_keywords`)
3. **선정 기준**: Gemini가 논쟁 소지 적은 생활·경제·과학·문화 소식만 선택, 없으면 그 회차는 게시 생략
4. **2차 팩트체크**: 별도 호출로 대본의 숫자·주체·결과를 근거 기사와 대조 → 경미하면 수정, 문제 있으면 탈락 후 다른 이슈로 재시도

---

## 1. 폴더 구성

| 경로 | 역할 |
|---|---|
| `config.yaml` | 계정명·슬롯·뉴스 피드·모델·컷 수·색상·안전 규칙 (**대부분의 조정은 여기서**) |
| `gtoon/news.py` | Google News·BBC RSS 수집, 관련 기사 수/키워드 겹침으로 화제성 점수 |
| `gtoon/script.py` | Gemini 1회 호출로 이슈 선정 + 6컷 대본 + 캡션·해시태그 |
| `gtoon/imagegen.py` | 그림 생성: Cloudflare → Pollinations → 대체 그림 순서로 자동 전환 |
| `gtoon/compose.py` | 1080×1350(4:5) 컷 합성, 말풍선·해설·표지·요약 페이지 |
| `gtoon/mascot.py` | 해설 캐릭터 '지구톤'(코드로 그려 매번 동일한 모습) |
| `gtoon/instagram.py` | 공식 API 캐러셀 게시, 토큰 갱신 |
| `workflows/daily.yml` → 저장소 `.github/workflows/`로 | 하루 3회 자동 실행 |
| `workflows/refresh-token.yml` → 〃 | (구형 60일 토큰일 때만) 자동 갱신 |
| `workflows/check-instagram.yml` → 〃 | 토큰·계정 연결 확인 |
| `data/history.json` | 게시 이력(중복 주제 방지) |
| `run_sample.bat` | 키 없이 샘플 렌더링 테스트 (Windows) |
| `sample_preview/` | 샘플 결과 6장 (그림 자리는 실제 운영 시 AI 개그 일러스트로 채워짐) |

## 2. 무료 한도 (2026-11 기준, 변동 가능)

- **Gemini API**: 이미지 생성은 무료 없음 → 대본(텍스트)만 사용. 무료 한도는 프로젝트별로 Google AI Studio에서 확인. 회차당 2~4회(대본+팩트체크) 호출이라 Flash 계열 무료 한도(보고상 하루 약 20회) 안에 들어가고, 초과 시 Flash-Lite로 자동 전환.
- **Cloudflare Workers AI**: 하루 10,000 뉴런 무료. FLUX-1-schnell 1024px·6스텝 ≈ 장당 약 77뉴런 → 하루 약 120장 가능(필요량 하루 12장).
- **Instagram API**: 24시간당 API 게시 50~100건(캐러셀 1건 = 1게시).
- **GitHub Actions**: 공개 저장소는 무료.

---

## 3. 설정 순서 (처음 1회, 약 1시간)

### ① 인스타그램 계정
1. 새 계정 생성 (예: `@global.toon`) → `config.yaml`의 `account.handle` 수정
2. 설정 → 계정 유형 → **프로페셔널 계정(크리에이터 또는 비즈니스)** 으로 전환

### ② Meta 개발자 앱 → 토큰 발급 (2026 통합 로그인 방식)
1. developers.facebook.com → 앱 만들기 → 사용 사례 **"Instagram에서 메시지 및 콘텐츠 관리"**
2. 이용 사례 맞춤 설정 → **API setup with Unified login** → **+ 비즈니스 포트폴리오** (없으면 새로 만들기)
3. business.facebook.com/settings → **계정 → Instagram 계정 → 추가**로 @globaltoonstoday 연결
4. **사용자 → 시스템 사용자 → 추가**(관리자) → **자산 할당**: 앱 + Instagram 계정
5. **토큰 생성**: 앱 선택, 만료 **사용 안 함**, 권한 `instagram_business_basic`, `instagram_business_content_publish` → 토큰 복사
6. Instagram 계정 화면의 **ID(숫자)** 복사
7. 연결 확인: GitHub 등록 후 Actions → **Check Instagram** 실행 (게시하지 않고 연결만 확인)

### ③ Gemini API 키
aistudio.google.com → Get API key → 키 복사

### ④ Cloudflare (그림 생성)
1. dash.cloudflare.com 무료 가입 → 우측의 **Account ID** 복사
2. 내 프로필 → API 토큰 → 토큰 생성 → 템플릿 **"Workers AI"** → 토큰 복사

### ⑤ GitHub 저장소
1. github.com에서 **Public** 저장소 `global-toon` 생성 (이미지를 공개 URL로 넘기기 위해 공개 필요. 비밀값은 코드에 없음)
2. 이 폴더 전체 업로드 (GitHub Desktop 권장)
   - **중요**: `workflows` 폴더의 `daily.yml`, `refresh-token.yml` 두 파일은 저장소의 `.github/workflows/` 경로에 있어야 동작합니다.
     (PC 보안상 `.github` 폴더를 직접 만들 수 없어 분리해 두었습니다. GitHub 웹에서 *Add file → Create new file* → 이름에 `.github/workflows/daily.yml` 입력 후 내용 붙여넣기 하면 가장 간단합니다.)
3. Settings → Secrets and variables → Actions → **Secrets**에 등록:

| 이름 | 값 |
|---|---|
| `GEMINI_API_KEY` | ③ |
| `CF_ACCOUNT_ID` / `CF_API_TOKEN` | ④ |
| `IG_ACCESS_TOKEN` / `IG_USER_ID` | ② |
| `GH_PAT` | (선택) 구형 60일 토큰 사용 시에만 필요 |

4. **Variables** 탭에 `AUTO_PUBLISH` = `false` 추가 → 처음 며칠은 **이미지 생성만** 하고 게시 안 함

### ⑥ 시험 실행
Actions → **Global Toon Daily** → Run workflow (slot `noon`, publish `false`)
→ 완료 후 실행 화면 하단 **Artifacts**에서 이미지·`script.json`(팩트체크 결과 포함) 다운로드해 확인

### ⑦ 본격 가동
품질이 괜찮으면 `AUTO_PUBLISH` 를 `true`로 변경 → 매일 3회 자동 게시

---

## 4. 운영 팁

- **실패 알림**: 실패 시 GitHub이 메일로 알림. 대부분 원인은 토큰 만료(→ ② 재발급 후 Secret 교체) 또는 무료 한도 초과.
- **화풍 변경**: `config.yaml`의 `comic.style_prompt`, `theme_color`
- **게시량 조정**: `daily.yml`의 cron 줄 추가/삭제 + `config.yaml` slots
- **이미지 품질 업그레이드**: `image.cloudflare_model`을 `@cf/black-forest-labs/flux-2-klein-4b` 등으로 변경(뉴런 소모 증가, 무료 범위 내 가능)
- **로컬 테스트**: `run_sample.bat` 실행 → `output\날짜\noon\` 에 6장 생성

## 5. 리스크 관리 (콘텐츠 정책)

- 실존 인물 얼굴·로고는 그리지 않도록 프롬프트에 고정 (`safety.rules`)
- 참사 희화화·성범죄·특정 정당 지지·미확인 루머는 선정에서 제외 (`safety.skip_topics`)
- 기사 원문을 복제하지 않고 제목·관련 제목만 근거로 재서술, 캡션에 출처·AI 생성 표기
- 공식 Instagram API만 사용(비공식 자동 로그인 방식은 계정 정지 위험)
- 사실 오류 가능성은 남아 있으므로, 초기에는 `AUTO_PUBLISH=false`로 검수 후 게시 권장
