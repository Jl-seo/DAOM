# 3. 백엔드 가이드

> FastAPI 기반 백엔드의 구조, 서비스 레이어, 데이터베이스 패턴, 설정 체계를 설명합니다.

---

## 📁 디렉토리 구조

```
backend/
├── main.py                      # FastAPI 앱 엔트리포인트 (lifespan 관리)
├── app/
│   ├── api/
│   │   ├── api.py               # 라우터 통합 (/api/v1 접두사)
│   │   └── endpoints/           # 기능별 API 엔드포인트
│   │       ├── models.py        # 추출 모델 CRUD
│   │       ├── extraction_preview.py  # 추출 실행 + 프리뷰 (43KB, 최대)
│   │       ├── documents.py     # 문서 관리
│   │       ├── users.py         # 사용자 관리
│   │       ├── groups.py        # 그룹 관리
│   │       ├── audit.py         # 감사 로그 조회
│   │       ├── settings.py      # 시스템 설정 API
│   │       ├── site_settings.py # 사이트 설정 (메뉴, UI)
│   │       ├── menus.py         # 메뉴 구성
│   │       ├── prompts.py       # 프롬프트 관리
│   │       ├── power_automate.py # Power Automate 연동
│   │       ├── graph.py         # Microsoft Graph API
│   │       ├── transformation.py # 데이터 변환
│   │       ├── templates.py     # 템플릿
│   │       └── extraction/      # 추출 관련 하위 라우터
│   │
│   ├── core/
│   │   ├── config.py            # 모든 환경변수 정의 (Pydantic Settings)
│   │   ├── auth.py              # JWT 검증, 인증 미들웨어
│   │   └── security.py          # SSRF 방어, URL 검증
│   │
│   ├── db/
│   │   └── cosmos.py            # Cosmos DB 클라이언트 (싱글톤, 7개 컨테이너)
│   │
│   ├── schemas/                 # Pydantic 요청/응답 스키마
│   │
│   └── services/                # 비즈니스 로직 (핵심)
│
├── Dockerfile                   # python:3.12-slim 기반
└── requirements.txt             # pip 의존성 (76개)
```

---

## 🧩 서비스 레이어 맵

> 서비스 파일은 `app/services/` 에 위치하며, **비즈니스 로직의 핵심**입니다.

### 추출 관련 (Extract Pipeline)

| 서비스 | 크기 | 역할 |
|--------|------|------|
| `extraction_service.py` | 22KB | 추출 오케스트레이터 — 전체 흐름 제어 |
| `llm.py` | 37KB | LLM 호출, 프롬프트 실행, 응답 파싱 |
| `beta_chunking.py` | 36KB | 3-Tier 청킹 전략 (페이지, 싱글샷, 텍스트) |
| `layout_parser.py` | 20KB | OCR 결과 → 구조화된 레이아웃 변환 |
| `chunked_extraction.py` | 19KB | 레거시 청킹 추출 |
| `extraction_logs.py` | 16KB | 추출 로그 CRUD |
| `extraction_jobs.py` | 18KB | 비동기 추출 작업 관리 |
| `extraction_utils.py` | 9KB | 추출 유틸리티 (URL 검증, 데이터 정규화) |
| `doc_intel.py` | 11KB | Document Intelligence SDK 래퍼 |
| `refiner.py` | 9KB | OCR → LLM 프롬프트 정제 |
| `splitter.py` | 6KB | 텍스트/페이지 분할 |
| `prompt_service.py` | 8KB | 프롬프트 템플릿 관리 |

### 추출 파이프라인 (`extraction/` 하위 디렉토리)

| 서비스 | 역할 |
|--------|------|
| `extraction/beta_pipeline.py` | Beta 파이프라인 (3-Tier 청킹, Header Context Injection) |
| `extraction/orchestrator.py` | 파이프라인 오케스트레이터 |

### 변환 레이어 (`transformation/` 하위 디렉토리)

| 서비스 | 역할 |
|--------|------|
| `transformation/` | 추출 결과 후처리 (데이터 확장, 계산, 정규화) |

### 비교 및 비전

| 서비스 | 크기 | 역할 |
|--------|------|------|
| `vision_service.py` | 3KB | 이미지 비교용 비전 API |
| `pixel_diff.py` | 10KB | 픽셀 수준 이미지 비교 |

### 관리 및 인프라

| 서비스 | 크기 | 역할 |
|--------|------|------|
| `user_service.py` | 10KB | 사용자 CRUD, 대량 가져오기 |
| `group_service.py` | 10KB | 그룹/권한 관리 |
| `permission_service.py` | 7KB | RBAC 권한 해결 |
| `audit.py` | 8KB | 감사 로그 기록 |
| `token_audit.py` | 6KB | LLM 토큰 사용량 추적 |
| `menu_service.py` | 5KB | 사이드바 메뉴 관리 |
| `models.py` | 4KB | 추출 모델 CRUD |
| `stats_service.py` | 3KB | 통계/대시보드 데이터 |
| `storage.py` | 8KB | Azure Blob Storage 래퍼 |
| `file_storage.py` | 2KB | 파일 저장소 추상화 |
| `graph_service.py` | 4KB | Microsoft Graph API 호출 |
| `startup_service.py` | 6KB | 앱 시작 시 초기화 로직 |
| `template_chat.py` | 6KB | 템플릿 기반 채팅 |
| `webhook.py` | 1KB | 외부 웹훅 처리 |

---

## 🔌 API 엔드포인트 구조

모든 API는 `/api/v1` 접두사를 사용합니다.

### 주요 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/models` | 추출 모델 목록 조회 |
| `POST` | `/models` | 추출 모델 생성 |
| `PUT` | `/models/{id}` | 추출 모델 수정 |
| `DELETE` | `/models/{id}` | 추출 모델 삭제 (soft delete) |
| `POST` | `/extract` | 추출 실행 (파일 업로드 + 모델 선택) |
| `GET` | `/extraction-logs` | 추출 로그 목록 |
| `GET` | `/extraction-logs/{id}` | 추출 로그 상세 |
| `POST` | `/extraction-jobs` | 비동기 추출 작업 생성 |
| `GET` | `/extraction-jobs/{id}` | 작업 상태 조회 (폴링) |
| `GET` | `/users` | 사용자 목록 |
| `POST` | `/users` | 사용자 생성 |
| `GET` | `/groups` | 그룹 목록 |
| `GET` | `/audit-logs` | 감사 로그 조회 |
| `GET` | `/settings` | 시스템 설정 조회 |
| `PUT` | `/settings` | 시스템 설정 수정 |
| `POST` | `/power-automate/extract` | Power Automate 워크플로우 추출 |

---

## ⚙️ 설정 체계 (Configuration)

### config.py 주요 환경변수

```python
class Settings(BaseSettings):
    # ─── Azure Cosmos DB ───
    COSMOS_ENDPOINT: str = ""
    COSMOS_KEY: str = ""
    COSMOS_DATABASE: str = "daom"

    # ─── Azure Document Intelligence ───
    DOC_INTEL_ENDPOINT: str = ""
    DOC_INTEL_KEY: str = ""

    # ─── Azure AI Foundry (LLM) ───
    AI_FOUNDRY_ENDPOINT: str = ""
    AI_FOUNDRY_KEY: str = ""
    AI_FOUNDRY_DEPLOYMENT: str = "gpt-4o"
    AI_FOUNDRY_API_VERSION: str = "2024-12-01-preview"

    # ─── Blob Storage ───
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_STORAGE_CONTAINER_NAME: str = "documents"

    # ─── CORS ───
    CORS_ORIGINS: str = "http://localhost:5173"

    # ─── LLM 파라미터 ───
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.1

    # ─── 청킹 ───
    CHUNK_SIZE: int = 5000
    CHUNK_OVERLAP: int = 500
    EXTRACTION_CONCURRENCY: int = 3

    # ─── 보안 ───
    MAX_UPLOAD_SIZE: int = 52428800  # 50MB
```

### 설정 우선순위

```
Cosmos DB (system_config) > 모델별 설정 > 환경변수 (.env)
```

- **system_config**: 관리자가 UI에서 변경 가능한 런타임 설정
- **모델별 설정**: 각 `ExtractionModel`에 포함된 설정 (chunking, beta_features)
- **환경변수**: 인프라 레벨 기본값 (변경 시 재배포 필요)

---

## 💾 데이터 모델 (핵심)

### ExtractionModel (추출 모델)

```json
{
  "id": "model-uuid",
  "name": "Premium Rate Card",
  "description": "보험 프리미엄 요율표 추출",
  "is_active": true,               // soft delete 지원
  "tenant_id": "tenant-uuid",
  
  "fields": [                       // 추출할 필드 정의
    {
      "key": "premium_rate",
      "label": "프리미엄 요율",
      "type": "table",              // text, number, date, table, image
      "description": "요율 테이블 데이터",
      "children": [                  // 중첩 필드 (테이블 컬럼)
        { "key": "age_group", "label": "연령대", "type": "text" },
        { "key": "rate", "label": "요율", "type": "number" }
      ]
    }
  ],
  
  "global_rules": "...",            // LLM에 전달되는 전역 규칙
  "reference_data": "...",          // 참조 데이터 (코드표 등)
  
  "beta_features": {                // 실험적 기능 토글
    "use_optimized_prompt": false,
    "use_virtual_excel_ocr": false
  },
  
  "created_at": "2026-01-15T...",
  "updated_at": "2026-02-09T..."
}
```

### ExtractionLog (추출 결과)

```json
{
  "id": "log-uuid",
  "model_id": "model-uuid",         // partition key
  "tenant_id": "tenant-uuid",
  "user_id": "user-uuid",
  "type": "extraction",
  "status": "completed",            // pending, processing, completed, failed
  
  "file_name": "document.pdf",
  "file_url": "https://blob.../document.pdf",
  
  "extracted_data": {               // 추출 결과
    "guide_extracted": {            // ← 필수 래퍼
      "premium_rate": [
        { "age_group": "20-30", "rate": 1.5 },
        { "age_group": "31-40", "rate": 2.3 }
      ]
    }
  },
  
  "preview_data": { ... },         // PDF 미리보기 메타데이터
  "debug_data": { ... },           // 디버그 정보 (프롬프트, 토큰)
  
  "token_usage": {                  // LLM 토큰 사용량
    "prompt_tokens": 1500,
    "completion_tokens": 800,
    "total_tokens": 2300
  },
  
  "processing_time_ms": 12500,
  "created_at": "2026-02-09T..."
}
```

> **⚠️ 중요**: 추출 결과는 반드시 `guide_extracted` 래퍼 안에 포함됩니다. 이 계약을 어기면 프론트엔드에서 결과를 파싱할 수 없습니다.

---

## 🔧 새 API 엔드포인트 추가 방법

### 1. 스키마 정의 (`app/schemas/`)

```python
# app/schemas/my_feature.py
from pydantic import BaseModel

class MyFeatureRequest(BaseModel):
    name: str
    value: int

class MyFeatureResponse(BaseModel):
    id: str
    name: str
    status: str
```

### 2. 서비스 로직 (`app/services/`)

```python
# app/services/my_feature_service.py
from app.db.cosmos import get_container

async def create_feature(data: dict, tenant_id: str) -> dict:
    container = get_container("my_container", "/tenant_id")
    item = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,  # 필수! 테넌트 격리
        **data
    }
    container.create_item(body=item)
    return item
```

### 3. 엔드포인트 등록 (`app/api/endpoints/`)

```python
# app/api/endpoints/my_feature.py
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/my-features", tags=["My Features"])

@router.post("/", response_model=MyFeatureResponse)
async def create(request: MyFeatureRequest, user=Depends(get_current_user)):
    return await my_feature_service.create_feature(
        data=request.dict(),
        tenant_id=user.tenant_id  # 테넌트 격리은 필수
    )
```

### 4. 라우터 등록 (`app/api/api.py`)

```python
from app.api.endpoints import my_feature
api_router.include_router(my_feature.router)
```

---

## 📌 핵심 패턴 & 규칙

### 1. 테넌트 격리 (필수)
```python
# ✅ 올바름: 모든 쿼리에 tenant_id 포함
items = container.query_items(
    query="SELECT * FROM c WHERE c.tenant_id=@tid",
    parameters=[{"name": "@tid", "value": tenant_id}]
)

# ❌ 위험: tenant_id 없이 쿼리
items = container.query_items("SELECT * FROM c WHERE c.id=@id", ...)
```

### 2. Soft Delete
```python
# 모델 삭제 시 is_active를 false로 변경 (실제 삭제 X)
model["is_active"] = False
container.upsert_item(model)
```

### 3. Lifespan 패턴
```python
# main.py — 앱 시작/종료 시 실행
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_cosmos()          # DB 연결 초기화
    startup_service.run()  # 초기 데이터 로드
    yield
    # 정리 작업
```

### 4. 에러 핸들링
```python
from fastapi import HTTPException

# 구조화된 에러 응답
raise HTTPException(
    status_code=404,
    detail={"error": "MODEL_NOT_FOUND", "message": "모델을 찾을 수 없습니다"}
)
```

---

**다음**: [04. 프론트엔드 가이드](04-frontend.md)에서 React SPA의 구조와 주요 컴포넌트를 살펴봅니다.
