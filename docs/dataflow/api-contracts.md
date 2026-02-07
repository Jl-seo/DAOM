# API 엔드포인트 & 데이터 스키마

> 추출 관련 핵심 API 엔드포인트와 요청/응답 스키마 정리

---

## 추출 관련 API (extraction_preview.py)

Base path: `/extraction`

### 핵심 엔드포인트

---

#### POST `/upload-and-start`
파일 업로드 + 추출 Job 시작 (FormData)

**Request (multipart/form-data):**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `file` | File | ✅ | 문서 파일 (PDF) |
| `candidate_files` | File[] | ❌ | 비교 모델용 후보 파일들 |
| `model_id` | string | ✅ | 모델 ID |

**Response:**
```json
{
  "job_id": "uuid-string",
  "status": "P100",
  "log_id": "log-uuid"
}
```

---

#### GET `/job/{job_id}`
Job 상태 폴링

**Response:**
```json
{
  "job_id": "uuid",
  "status": "S100",                    // P100, P200, S100, E100, ANALYZING, REFINING
  "preview_data": {                    // 전체 미리보기 데이터
    "sub_documents": [{
      "doc_type": "main",
      "data": {
        "guide_extracted": {
          "field_key": { "value": "값", "confidence": 0.95, "bbox": {...} }
        },
        "other_data": [...],
        "_beta_parsed_content": "..."  // Beta 모드시만
      }
    }],
    "raw_content": "OCR 전체 텍스트",
    "raw_tables": [{ "cells": [...], "rowCount": 5, "columnCount": 3 }]
  },
  "extracted_data": {                  // guide_extracted 평탄화 (편의용)
    "field_key": { "value": "값", "confidence": 0.95 }
  },
  "error": null,                       // E100 시 에러 메시지
  "filename": "document.pdf",
  "file_url": "https://blob.../doc.pdf",
  "candidate_file_urls": [],           // 비교 모델용
  "log_id": "log-uuid",
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

---

#### PUT `/job/{job_id}/confirm`
추출 결과 확정 (사용자 수정 저장)

**Request:**
```json
{
  "guide_extracted": { "field_key": { "value": "수정값" } },
  "other_data": [...],
  "selected_columns": ["col1", "col2"]
}
```

---

#### POST `/job/{job_id}/retry` (via `retry_extraction`)
기존 로그 기반 재추출

---

#### GET `/logs/{model_id}`
모델별 추출 기록 조회

**Response:**
```json
[
  {
    "id": "log-uuid",
    "model_id": "model-uuid",
    "filename": "doc.pdf",
    "status": "S100",
    "created_at": "ISO8601",
    "created_by": "user@email.com",
    "guide_extracted": {...},
    "other_data": [...]
  }
]
```

---

#### GET `/log/{log_id}`
단일 추출 기록 (딥링크용)

---

## 모델 API (models.py)

Base path: `/models`

| Method | Path | 설명 |
|--------|------|------|
| GET | `/` | 전체 모델 목록 |
| GET | `/{id}` | 모델 상세 (필드 정의 포함) |
| POST | `/` | 모델 생성 |
| PUT | `/{id}` | 모델 수정 |
| DELETE | `/{id}` | 모델 삭제 |

**Model 스키마:**
```json
{
  "id": "uuid",
  "name": "모델명",
  "description": "설명",
  "model_type": "extraction",         // "extraction" | "comparison"
  "is_active": true,
  "fields": [
    { "key": "field1", "label": "필드1", "type": "text", "required": true }
  ],
  "excel_columns": [...],
  "beta_features": {
    "use_optimized_prompt": false,     // Beta LayoutParser 사용 여부
    "use_virtual_excel_ocr": false
  },
  "system_prompt": "...",             // 커스텀 LLM 프롬프트
  "created_at": "ISO8601"
}
```

---

## 기타 API

| Base Path | 파일 | 설명 |
|-----------|------|------|
| `/audit` | `audit.py` | 활동 로그 조회 |
| `/documents` | `documents.py` | 문서 관리 |
| `/groups` | `groups.py` | 그룹/권한 관리 |
| `/menus` | `menus.py` | 메뉴 구성 |
| `/settings` | `settings.py` | 시스템 설정 |
| `/site-settings` | `site_settings.py` | 사이트 외관 (로고, 테마) |
| `/users` | `users.py` | 사용자 관리 |
| `/prompts` | `prompts.py` | 프롬프트 CRUD |
| `/power-automate` | `power_automate.py` | 외부 연동 |
| `/transformation` | `transformation.py` | 데이터 변환 |
