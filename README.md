# DAOM (Document AI Orchestration Manager)

> 비정형 문서를 AI로 정형화하는 엔터프라이즈 솔루션

## 📋 개요

DAOM은 Azure AI Document Intelligence와 GPT를 결합하여 비정형 문서(PDF, 이미지)에서 구조화된 데이터를 자동으로 추출하는 웹 애플리케이션입니다. 사용자는 추출 모델을 직접 정의하고, AI가 문서를 분석하여 원하는 형식으로 데이터를 추출합니다.

### 주요 특징

- **🤖 AI 기반 문서 분석**: Azure Document Intelligence + GPT를 활용한 고정밀 데이터 추출
- **🎨 커스텀 모델 정의**: 추출하고 싶은 필드를 직접 정의하여 모델 생성
- **📊 실시간 검증 UI**: 추출된 데이터를 PDF와 함께 보며 실시간 수정 가능
- **🔄 재시도 및 이력 관리**: 추출 실패 시 재시도, 전체 추출 이력 관리
- **⚡ OCR 캐싱**: 재시도 시 OCR 결과를 캐시하여 95% 빠른 처리
- **👥 멀티 테넌트**: Entra ID 기반 인증 및 권한 관리
- **📦 대용량 문서 처리**: 페이지별 청킹으로 토큰 제한 극복

---

## 🏗️ 아키텍처

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│   React SPA     │─────▶│  FastAPI Backend │─────▶│  Azure Services │
│  (TypeScript)   │      │     (Python)     │      │                 │
└─────────────────┘      └──────────────────┘      │ - Document AI   │
                                                    │ - OpenAI GPT    │
                                                    │ - Blob Storage  │
                                                    │ - Cosmos DB     │
                                                    └─────────────────┘
```

### 기술 스택

**Frontend**
- React 18 + TypeScript
- TanStack Query (React Query)
- TanStack Table
- Tailwind CSS + shadcn/ui
- Framer Motion
- React PDF Viewer

**Backend**
- FastAPI (Python 3.11+)
- Azure AI Document Intelligence SDK
- Azure OpenAI SDK
- Azure Cosmos DB
- Azure Blob Storage
- MSAL (Microsoft Authentication Library)

**Infrastructure**
- Azure Container Apps
- Azure Container Registry (ACR)
- GitHub Actions (CI/CD)
- Docker

---

## 🚀 시작하기

### 사전 요구사항

- Node.js 18+
- Python 3.11+
- Azure 구독 (Document Intelligence, OpenAI, Cosmos DB, Blob Storage)
- Entra ID 앱 등록

### 환경 변수 설정

#### Backend (.env)

```bash
# Azure Document Intelligence
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=your-key

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4

# Azure Blob Storage
AZURE_STORAGE_CONNECTION_STRING=your-connection-string
AZURE_STORAGE_CONTAINER_NAME=daom-uploads

# Azure Cosmos DB
COSMOS_ENDPOINT=https://your-account.documents.azure.com:443/
COSMOS_KEY=your-key
COSMOS_DATABASE_NAME=daom
COSMOS_CONTAINER_NAME=extraction_jobs

# Entra ID
AZURE_CLIENT_ID=your-client-id
AZURE_TENANT_ID=your-tenant-id

# CORS
ALLOWED_ORIGINS=http://localhost:5173,https://your-frontend-url
```

#### Frontend (.env)

```bash
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_MSAL_CLIENT_ID=your-client-id
VITE_MSAL_AUTHORITY=https://login.microsoftonline.com/your-tenant-id
VITE_MSAL_REDIRECT_URI=http://localhost:5173
```

### 로컬 실행

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:5173` 접속

---

## 📖 주요 기능

### 1. 모델 스튜디오

사용자가 직접 추출 모델을 정의할 수 있습니다.

**모델 구성 요소:**
- **필드 정의**: 추출할 데이터 항목 (예: 계약서 번호, 날짜, 금액)
- **필드 타입**: `string`, `number`, `date`, `boolean`, `array`
- **설명**: AI가 필드를 이해하도록 돕는 힌트

**예시:**
```json
{
  "model_name": "국외거래 신고서",
  "fields": [
    {
      "key": "report_title",
      "label": "보고서 제목",
      "type": "string",
      "description": "문서 상단의 제목"
    },
    {
      "key": "foreign_company_name",
      "label": "해외기업명",
      "type": "string"
    },
    {
      "key": "contract_date",
      "label": "계약 기표일",
      "type": "date"
    }
  ]
}
```

### 2. 문서 추출 프로세스

```
파일 업로드 → OCR (Document Intelligence) → AI 분석 (GPT) → 데이터 검증 → 저장
```

1. **파일 업로드**: PDF 또는 이미지 파일 업로드
2. **OCR 처리**: Azure Document Intelligence가 텍스트, 표, 레이아웃 추출
3. **AI 분석**: GPT가 모델 정의에 따라 데이터 추출
4. **실시간 검증**: 사용자가 추출된 데이터를 PDF와 함께 검토
5. **수정 및 저장**: 필요 시 수정 후 최종 저장

### 3. 검증 UI

- **PDF 뷰어**: 원본 문서 표시
- **데이터 테이블**: 추출된 데이터를 편집 가능한 테이블로 표시
- **하이라이팅**: 클릭 시 PDF에서 해당 위치 강조 표시
- **실시간 수정**: 테이블에서 직접 데이터 수정 가능

### 4. 대용량 문서 처리 (청킹)

토큰 제한을 극복하기 위한 페이지별 청킹 전략:

```python
# backend/app/services/chunked_extraction.py
# 문서를 페이지 단위로 분할하여 병렬 처리
# 각 청크는 독립적으로 GPT에 전송
# 결과를 병합하여 최종 데이터 생성
```

**특징:**
- 최대 토큰 수 초과 시 자동으로 청킹 모드 전환
- 페이지별 병렬 처리로 속도 향상
- Semaphore로 동시 호출 수 제한 (Rate Limit 방지)

### 5. 추출 이력 관리

- **개인 이력**: 내가 추출한 문서 목록
- **전체 이력**: 모든 사용자의 추출 기록 (관리자)
- **필터링**: 상태, 모델, 사용자별 필터
- **재시도**: 실패한 추출 재시도
- **일괄 다운로드**: 여러 추출 결과를 Excel로 일괄 다운로드

---

## 🔐 권한 관리

### 역할 기반 접근 제어 (RBAC)

- **System Admins**: 모든 기능 접근 가능
- **Model Editors**: 모델 생성/수정 가능
- **일반 사용자**: 문서 추출 및 개인 이력 조회

### Entra ID 그룹 관리

관리자 페이지에서 Entra ID 그룹 멤버 관리:
- System Admins 그룹 멤버 추가/제거
- Model Editors 그룹 멤버 추가/제거

---

## 🎨 UI/UX 특징

### 테마 시스템

- **라이트/다크 모드**: 시스템 설정 또는 수동 전환
- **커스터마이징**: 관리자가 브랜드 컬러 변경 가능
- **Cosmos DB 저장**: 테마 설정 영구 저장

### 애니메이션

- **Magic UI**: 진행 상태 표시에 그라데이션, 글로우, 시머 효과
- **Framer Motion**: 부드러운 페이지 전환 및 인터랙션
- **로딩 상태**: 원형 프로그레스, 단계별 인디케이터

### 반응형 디자인

- 데스크톱, 태블릿, 모바일 모두 지원
- 모바일에서 카메라 직접 촬영 지원 (빠른 추출)

---

## 📊 데이터 모델

### ExtractionLog (추출 기록)

```typescript
{
  id: string
  user_id: string
  model_id: string
  filename: string
  file_url: string
  status: 'P100' | 'P200' | 'P300' | 'S100' | 'S200' | 'E100'
  extracted_data: Record<string, any>
  preview_data: {
    sub_documents: Array<{
      index: number
      page_ranges: number[]
      data: {
        guide_extracted: Record<string, FieldValue>
        other_data: Array<any>
      }
    }>
  }
  created_at: string
  updated_at: string
}
```

### ExtractionJob (처리 작업)

```typescript
{
  id: string
  status: 'P100' | 'P200' | 'P300' | 'S100' | 'E100'
  filename: string
  file_url: string
  preview_data: any
  error?: string
  original_log_id?: string  // 재시도 시 원본 로그 참조
  created_at: string
  updated_at: string
}
```

### 상태 코드

- **P100**: 대기 중 (Pending)
- **P200**: OCR 처리 중 (Processing)
- **P300**: AI 분석 중 (Analyzing)
- **S100**: 추출 완료 (Success)
- **S200**: 검증 완료 (Confirmed)
- **E100**: 오류 (Error)
- **E300**: 취소됨 (Cancelled)

---

## 🚢 배포

### GitHub Actions CI/CD

#### 테스트 배포 (feature/*, fix/* 브랜치)

```yaml
# .github/workflows/deploy-test-backend.yml
# .github/workflows/deploy-test-frontend.yml
# feature/* 또는 fix/* 브랜치 푸시 시 자동 배포
# Azure Container Registry 사용
```

#### 프로덕션 배포 (main 브랜치)

```yaml
# .github/workflows/deploy-frontend.yml
# .github/workflows/deploy-backend.yml
# main 브랜치 푸시 시 프로덕션 배포
```

### Azure Container Apps

**Frontend Container**
- 포트: 80
- 환경 변수: VITE_* 빌드 시 주입
- 최소 인스턴스: 1

**Backend Container**
- 포트: 8000
- 환경 변수: Azure 리소스 연결 정보
- 최소 인스턴스: 1
- 스케일링: CPU/메모리 기반

---

## 🐛 트러블슈팅

### 1. 토큰 제한 초과 (429 Error)

**증상**: 대용량 문서 처리 시 "Token limit exceeded" 에러

**해결**:
- 자동으로 청킹 모드로 전환됨
- `backend/app/services/chunked_extraction.py` 참조
- `max_tokens_per_chunk` 조정 가능

### 2. 무한 폴링

**증상**: 추출 완료 후에도 계속 폴링

**해결**:
- 최대 폴링 시도 횟수 제한 (60회 = 5분)
- 500 에러 3회 이상 시 자동 중단
- 파일 업로드 시 기존 폴링 정리

### 3. 재시도 불가

**증상**: "재시도할 수 없습니다" 메시지

**해결**:
- 폴링 성공 시 `log_id` 설정 확인
- 백엔드 job 응답에 `log_id` 포함 확인
- `ExtractionContext.tsx` 참조

### 4. 빠른 추출 업로드 실패

**증상**: 빠른 추출에서 파일 업로드 안 됨

**해결**:
- 엔드포인트 확인: `/extraction/start-job` 사용
- `frontend/src/lib/api.ts` 의 `uploadFile` 함수 확인

---

## 📁 프로젝트 구조

```
daom/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── endpoints/
│   │   │       ├── extraction/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── jobs.py
│   │   │       │   └── logs.py
│   │   │       ├── extraction_preview.py
│   │   │       ├── models.py
│   │   │       ├── site_settings.py
│   │   │       └── users.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── enums.py
│   │   │   └── security.py
│   │   ├── services/
│   │   │   ├── chunked_extraction.py  # 청킹 로직
│   │   │   ├── doc_intel.py           # Document Intelligence
│   │   │   ├── extraction_jobs.py     # Job 관리
│   │   │   ├── extraction_logs.py     # Log 관리
│   │   │   ├── extraction_service.py  # 메인 추출 로직
│   │   │   └── llm.py                 # GPT 호출
│   │   └── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   └── ui/                    # shadcn/ui 컴포넌트
│   │   ├── features/
│   │   │   ├── extraction/            # 추출 이력
│   │   │   ├── models/                # 모델 스튜디오
│   │   │   ├── quick/                 # 빠른 추출
│   │   │   └── verification/          # 검증 UI
│   │   ├── hooks/
│   │   │   └── useExtractionActions.ts
│   │   ├── lib/
│   │   │   └── api.ts                 # API 클라이언트
│   │   ├── utils/
│   │   │   └── date.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
├── .github/
│   └── workflows/
│       ├── deploy-frontend.yml
│       ├── deploy-backend.yml
│       ├── deploy-test-frontend.yml
│       └── deploy-test-backend.yml
└── README.md
```

---

## 🤝 기여

이 프로젝트는 내부 엔터프라이즈 솔루션입니다.

---

## 📝 라이선스

Proprietary - All Rights Reserved

---

## 📞 문의

프로젝트 관련 문의사항은 팀 내부 채널을 이용해 주세요.
