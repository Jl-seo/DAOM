# 1. 시작하기 — 로컬 개발 환경 설정

> DAOM 프로젝트를 처음 시작하는 개발자를 위한 환경 설정 가이드입니다.

---

## 📋 사전 요구사항

| 도구 | 최소 버전 | 확인 명령어 |
|------|-----------|------------|
| **Python** | 3.12+ | `python --version` |
| **Node.js** | 20+ | `node --version` |
| **npm** | 9+ | `npm --version` |
| **Git** | 2.40+ | `git --version` |
| **Azure CLI** | 2.50+ | `az --version` (배포 시 필요) |

---

## 🔧 백엔드 설정

### 1. 프로젝트 클론 및 가상환경

```bash
git clone <repository-url>
cd daom/backend

# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate    # macOS/Linux
# venv\Scripts\activate     # Windows

# 의존성 설치
pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env` 파일을 `backend/` 디렉토리에 생성합니다:

```env
# ─── Azure Cosmos DB ───
COSMOS_ENDPOINT=https://your-cosmos.documents.azure.com:443/
COSMOS_KEY=your-cosmos-primary-key
COSMOS_DATABASE=daom

# ─── Azure Document Intelligence (OCR) ───
DOC_INTEL_ENDPOINT=https://your-docintel.cognitiveservices.azure.com/
DOC_INTEL_KEY=your-doc-intel-key

# ─── Azure AI Foundry (LLM) ─── 
AI_FOUNDRY_ENDPOINT=https://your-ai-foundry.openai.azure.com/
AI_FOUNDRY_KEY=your-ai-foundry-key
AI_FOUNDRY_DEPLOYMENT=gpt-4o        # LLM 모델 배포 이름
AI_FOUNDRY_API_VERSION=2024-12-01-preview

# ─── Azure Blob Storage ───
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
AZURE_STORAGE_CONTAINER_NAME=documents

# ─── 인증 (Entra ID) ───
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret   # 선택적

# ─── CORS ───
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# ─── 선택적 설정 ───
# LLM_MAX_TOKENS=4096                    # LLM 최대 출력 토큰
# LLM_TEMPERATURE=0.1                    # LLM 응답 다양성 (0~1)
# CHUNK_SIZE=5000                        # 텍스트 청킹 크기
# CHUNK_OVERLAP=500                      # 청킹 오버랩
# EXTRACTION_CONCURRENCY=3              # 동시 추출 작업 수
# MAX_UPLOAD_SIZE=52428800              # 최대 업로드 크기 (50MB)
```

> **⚠️ 주의**: `COSMOS_ENDPOINT`, `DOC_INTEL_ENDPOINT`, `AI_FOUNDRY_ENDPOINT`는 **필수값**입니다. 누락 시 앱 시작 시 경고가 출력됩니다.

### 3. 백엔드 실행

```bash
# 개발 모드 (자동 리로드)
uvicorn main:app --reload --port 8000

# 또는 gunicorn (프로덕션 유사 환경)
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 4. 실행 확인

```bash
# 헬스체크
curl http://localhost:8000/health

# API 문서 (Swagger UI)
open http://localhost:8000/docs

# OpenAPI 스키마
curl http://localhost:8000/openapi.json
```

---

## 🎨 프론트엔드 설정

### 1. 의존성 설치

```bash
cd daom/frontend

# 의존성 설치
npm install
```

### 2. 환경변수 설정

`.env` 파일을 `frontend/` 디렉토리에 생성합니다:

```env
# ─── 백엔드 API URL ───
VITE_API_BASE_URL=http://localhost:8000/api/v1

# ─── Azure 인증 (Entra ID) ───
VITE_AZURE_TENANT_ID=your-tenant-id
VITE_AZURE_CLIENT_ID=your-frontend-client-id
```

### 3. 프론트엔드 실행

```bash
# 개발 모드 (HMR 지원)
npm run dev

# → http://localhost:5173 에서 접속 가능
```

### 4. 기타 명령어

```bash
# 빌드 (프로덕션)
npm run build

# 타입 체크 + 빌드
tsc -b && vite build

# 린트
npm run lint

# 테스트
npm run test

# 빌드 결과 미리보기
npm run preview
```

---

## ✅ 환경 검증 체크리스트

| # | 확인 항목 | 방법 |
|---|----------|------|
| 1 | 백엔드 시작 성공 | `uvicorn main:app --reload` → 에러 없이 시작 |
| 2 | Cosmos DB 연결 | 로그에서 `[Cosmos] Connected to` 메시지 확인 |
| 3 | API 문서 접속 | `http://localhost:8000/docs` 열기 |
| 4 | 프론트엔드 시작 | `npm run dev` → `http://localhost:5173` 접속 |
| 5 | API 통신 | 프론트엔드에서 로그인 후 모델 목록 로딩 확인 |
| 6 | 파일 업로드 | Blob Storage 연결 후 문서 업로드 테스트 |

---

## 🔍 프로젝트 디렉토리 구조

```
daom/
├── backend/                  # FastAPI 백엔드
│   ├── app/
│   │   ├── api/              # API 라우터 & 엔드포인트
│   │   │   └── endpoints/    # 기능별 API (models, users, extraction, ...)
│   │   ├── core/             # 설정, 인증, 보안
│   │   ├── db/               # Cosmos DB 클라이언트, 컨테이너 정의
│   │   ├── schemas/          # Pydantic 모델 (요청/응답 스키마)
│   │   └── services/         # 비즈니스 로직 (30개 서비스)
│   │       ├── extraction/   # 추출 파이프라인 (beta_pipeline, orchestrator)
│   │       └── transformation/ # 데이터 변환 레이어
│   ├── main.py               # FastAPI 앱 엔트리포인트
│   ├── Dockerfile            # Python 3.12 slim 이미지
│   └── requirements.txt      # Python 의존성 (76개)
│
├── frontend/                 # React SPA
│   ├── src/
│   │   ├── App.tsx           # 앱 진입점, 라우터 설정
│   │   ├── components/       # 공유 컴포넌트 (23 파일 + 6 하위 디렉토리)
│   │   ├── features/         # 기능별 모듈
│   │   │   ├── extraction/   # 데이터 추출 관련
│   │   │   ├── comparison/   # 비교 분석 관련
│   │   │   ├── verification/ # 검증/리뷰 관련 (20 파일)
│   │   │   └── quick/        # 빠른 추출
│   │   ├── hooks/            # 커스텀 훅
│   │   ├── i18n/             # 다국어 번역 파일 (ko, en)
│   │   ├── lib/              # API 유틸리티, 공용 라이브러리
│   │   ├── types/            # TypeScript 타입 정의
│   │   └── utils/            # 유틸리티 함수
│   ├── Dockerfile            # Node 20 → Nginx 멀티스테이지 빌드
│   └── package.json          # npm 의존성
│
├── docs/                     # 문서
│   ├── HANDOVER.md           # ← 이 매뉴얼의 목차
│   ├── handover/             # 핸드오버 문서 (9개)
│   ├── ARCHITECTURE.md       # 시스템 아키텍처 개요
│   ├── SYSTEM.md             # 상세 시스템 명세
│   └── dataflow/             # 데이터 플로우 문서
│
└── .github/workflows/        # CI/CD 파이프라인
    ├── deploy-backend.yml     # 백엔드 배포 (master / feature)
    ├── deploy-frontend.yml    # 프론트엔드 배포
    ├── deploy-test-backend.yml  # 테스트 환경 백엔드
    └── deploy-test-frontend.yml # 테스트 환경 프론트엔드
```

---

## ❓ 자주 하는 실수

### Cosmos DB 연결 실패
```
[Cosmos] No credentials configured, using local JSON fallback
```
→ `.env` 파일에서 `COSMOS_ENDPOINT`와 `COSMOS_KEY`가 올바르게 설정되었는지 확인

### CORS 에러
```
Access-Control-Allow-Origin header missing
```
→ `.env`의 `CORS_ORIGINS`에 프론트엔드 URL(`http://localhost:5173`) 추가

### 프론트엔드 빌드 실패
```
error TS6133: 'xxx' is declared but its value is never read
```
→ TypeScript strict 모드 사용 중. 사용하지 않는 import/변수를 제거하세요.

---

**다음 단계**: [02. 시스템 아키텍처](02-architecture.md)를 읽어 전체 시스템 구조를 파악하세요.
