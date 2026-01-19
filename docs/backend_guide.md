# DAOM 백엔드 아키텍처 가이드

> FastAPI 기반 백엔드 시스템의 구조와 핵심 기능을 설명합니다.

---

## 📁 디렉토리 구조

```
backend/
├── main.py                 # 앱 진입점, CORS, 라우터 등록
├── app/
│   ├── api/               # API 엔드포인트
│   │   ├── api.py         # 라우터 통합
│   │   └── endpoints/     # 각 도메인별 라우터
│   ├── core/              # 설정 및 보안
│   │   └── config.py      # 환경변수 로딩
│   ├── db/                # 데이터베이스
│   │   └── cosmos.py      # Cosmos DB 연결
│   ├── models/            # Pydantic 모델
│   ├── schemas/           # API 요청/응답 스키마
│   └── services/          # 비즈니스 로직
```

---

## 🔌 API 엔드포인트

### 문서 관련
| 경로 | 메서드 | 설명 |
|------|--------|------|
| `/api/v1/documents/upload` | POST | 문서 업로드 + OCR 분석 |
| `/api/v1/documents/{id}` | GET | 문서 정보 조회 |

### 추출(Extraction) 관련
| 경로 | 메서드 | 설명 |
|------|--------|------|
| `/api/v1/extraction/preview` | POST | 실시간 추출 미리보기 |
| `/api/v1/extraction/logs` | GET | 추출 기록 목록 |
| `/api/v1/extraction/logs/{id}` | GET | 특정 추출 결과 조회 |
| `/api/v1/extraction/logs` | POST | 추출 결과 저장 |
| `/api/v1/extraction/jobs/{id}` | GET | 비동기 작업 상태 조회 |

### 모델 관리
| 경로 | 메서드 | 설명 |
|------|--------|------|
| `/api/v1/models` | GET | 모델 목록 조회 |
| `/api/v1/models` | POST | 새 모델 생성 |
| `/api/v1/models/{id}` | PUT | 모델 수정 |
| `/api/v1/models/{id}` | DELETE | 모델 삭제 |

### 설정
| 경로 | 메서드 | 설명 |
|------|--------|------|
| `/api/v1/settings/llm` | GET | LLM 설정 조회 |
| `/api/v1/settings/llm` | PUT | LLM 모델 변경 |
| `/api/v1/settings/site` | GET/PUT | 사이트 설정 |
| `/api/v1/settings/prompts` | GET | 시스템 프롬프트 목록 |
| `/api/v1/settings/prompts/{key}` | PUT | 프롬프트 수정 |

### 사용자 & 권한
| 경로 | 메서드 | 설명 |
|------|--------|------|
| `/api/v1/users/me` | GET | 현재 사용자 정보 |
| `/api/v1/groups` | GET/POST | 권한 그룹 CRUD |
| `/api/v1/groups/{id}/members` | POST/DELETE | 그룹 멤버 관리 |

---

## 💾 데이터베이스 스키마 (Cosmos DB)

### 컨테이너 목록
| 컨테이너 | 파티션 키 | 용도 |
|----------|----------|------|
| `models` | `/tenant_id` | 추출 모델 정의 |
| `extraction_logs` | `/tenant_id` | 추출 결과 기록 |
| `extraction_jobs` | `/id` | 비동기 작업 상태 |
| `groups` | `/tenant_id` | 권한 그룹 |
| `menus` | `/tenant_id` | 메뉴 설정 |
| `prompts` | `/id` | 시스템 프롬프트 |
| `config` | `/id` | 사이트 설정 |

### Model (추출 모델) 스키마
```json
{
  "id": "uuid",
  "tenant_id": "default",
  "name": "거래명세서",
  "fields": [
    {
      "key": "supplier_name",
      "label": "공급자명",
      "type": "string",
      "description": "공급하는 회사 이름"
    }
  ],
  "global_rules": "날짜는 YYYY-MM-DD 형식으로",
  "sample_docs": ["blob_url..."],
  "created_at": "2026-01-19T...",
  "updated_at": "2026-01-19T..."
}
```

### ExtractionLog (추출 결과) 스키마
```json
{
  "id": "uuid",
  "tenant_id": "default",
  "model_id": "model_uuid",
  "model_name": "거래명세서",
  "user_id": "user@company.com",
  "filename": "invoice_001.pdf",
  "status": "success",
  "data": {
    "supplier_name": {
      "value": "삼성전자",
      "confidence": 0.95,
      "bbox": [0.1, 0.2, 0.3, 0.4],
      "page_number": 1
    }
  },
  "created_at": "2026-01-19T..."
}
```

---

## 🛠️ 핵심 서비스

### extraction_service.py
**역할**: LLM 기반 데이터 추출

주요 기능:
- `analyze_document()`: 문서 분석 + LLM 추출
- `_call_llm_extraction()`: Azure OpenAI 호출
- 대용량 문서 자동 청킹 처리

### doc_intel.py
**역할**: Azure Document Intelligence (OCR) 연동

주요 기능:
- `analyze_document()`: PDF/이미지 → 텍스트 추출
- 바운딩 박스(좌표) 정보 추출

### llm.py
**역할**: Azure OpenAI 연결 관리

주요 기능:
- `get_current_model()`: 현재 LLM 모델명
- `set_llm_model()`: 모델 동적 변경
- `fetch_available_models()`: 사용 가능 모델 목록

### prompt_service.py
**역할**: 시스템 프롬프트 관리

주요 기능:
- DB 저장/조회 (5분 캐싱)
- 기본 프롬프트 제공
- 어드민에서 편집 가능

### storage.py
**역할**: Azure Blob Storage 연동

주요 기능:
- `upload_file()`: 문서 업로드
- `get_file_url()`: SAS URL 생성

---

## ⚙️ 환경변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `COSMOS_ENDPOINT` | ✅ | Cosmos DB 엔드포인트 |
| `COSMOS_KEY` | ✅ | Cosmos DB 키 |
| `COSMOS_DATABASE` | ✅ | 데이터베이스 이름 |
| `AZURE_FORM_ENDPOINT` | ✅ | Document Intelligence URL |
| `AZURE_FORM_KEY` | ✅ | Document Intelligence 키 |
| `AZURE_OPENAI_ENDPOINT` | ✅ | Azure OpenAI URL |
| `AZURE_OPENAI_API_KEY` | ✅ | Azure OpenAI 키 |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | ✅ | GPT 모델 배포명 |
| `AZURE_STORAGE_CONNECTION_STRING` | ✅ | Blob Storage 연결 |
| `BACKEND_CORS_ORIGINS` | ✅ | 허용 Origin (JSON 배열) |

---

## 🔒 인증 & 권한

### 인증 흐름
1. 프론트엔드에서 Entra ID 로그인
2. 액세스 토큰을 `Authorization: Bearer {token}` 헤더로 전송
3. 백엔드에서 토큰 검증 및 사용자 정보 추출

### 권한 모델
- **SuperAdmin**: 모든 권한
- **Admin (모델별)**: 해당 모델 편집 가능
- **User (모델별)**: 해당 모델 읽기/추출만 가능

---

## 🚀 로컬 실행

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# .env 파일 설정 후
uvicorn main:app --reload --port 8000
```

API 문서: http://localhost:8000/docs
