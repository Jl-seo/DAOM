# 프론트엔드 컴포넌트 구조

> 추출 관련 프론트엔드 컴포넌트 계층, 상태 관리, 데이터 흐름 정리

---

## 1. 컴포넌트 트리 (추출 흐름)

```
App.tsx
├─ AppLayout
│   ├─ Sidebar (collapsed/expanded)
│   │   └─ SidebarItem (tooltip, icon, label)
│   └─ <Routes>
│       └─ /models/:modelId → ModelView
│           └─ DocumentExtractionView ⭐ key={modelId}
│               └─ ExtractionProvider (Context)
│                   └─ ExtractionContainer
│                       ├─ ExtractionWizardHeader (step indicator)
│                       ├─ ExtractionHistoryView (activeStep === 'history')
│                       ├─ ExtractionUploadView (activeStep === 'upload')
│                       └─ ExtractionReviewView (activeStep === 'review')
│                           ├─ DocumentPreviewPanel (좌측)
│                           │   └─ PDFViewer
│                           │       ├─ PDF 렌더링 (react-pdf)
│                           │       ├─ 표 렌더링 (rawTables → cells grid)
│                           │       └─ OCR 텍스트 표시
│                           └─ DataReviewPanel (우측)
│                               ├─ 추출 데이터 탭 (guide_extracted)
│                               ├─ 기타 데이터 탭 (other_data)
│                               └─ Beta 파싱 탭 (조건: isBetaMode && parsedContent)
```

---

## 2. 상태 관리 (ExtractionContext)

`ExtractionContext.tsx` 가 추출 프로세스 전체 상태를 관리합니다.

### 핵심 State

| State | 타입 | 설명 | 출처 |
|-------|------|------|------|
| `model` | `ExtractionModel` | 현재 모델 정보 (필드 정의 포함) | `modelsApi.getById()` |
| `activeStep` | `ViewStep` | `'history'` → `'upload'` → `'review'` → `'complete'` | 내부 전환 |
| `status` | `ExtractionStatus` | `'idle'`/`'uploading'`/`'processing'`/`'S100'`/`'error'` | 폴링 응답 |
| `previewData` | `PreviewData` | 미리보기 전체 데이터 | `job.preview_data` |
| `result` | `Record<string,any>` | 추출 결과 (평탄화) | `job.extracted_data` |
| `file` | `File` | 업로드 파일 객체 | 사용자 선택 |
| `fileUrl` | `string` | Blob Storage URL | 업로드 응답 |
| `highlights` | `Highlight[]` | PDF 하이라이트 (bbox) | `previewData` 가공 |

### ViewStep 전환 흐름

```
history ─[새 추출]──→ upload ─[파일 선택]──→ (폴링) ─[S100]──→ review
  ↑                                                              │
  └──────────────────── [취소/리셋] ─────────────────────────────┘
```

### 폴링 메커니즘

```typescript
// ExtractionContext.tsx
// 3초 간격 폴링 → GET /extraction/job/{jobId}
// 종료 조건: status === 'S100' || status.startsWith('E')
// 성공시: previewData = data.preview_data, result = data.extracted_data
```

---

## 3. Sidebar 구조

### Props

| Prop | 타입 | 설명 |
|------|------|------|
| `collapsed` | `boolean` | 접기 모드 (아이콘만 표시) |
| `onToggleCollapse` | `() => void` | 접기/펼치기 토글 |
| `onClose` | `() => void` | 모바일 메뉴 닫기 |
| `className` | `string?` | 추가 CSS |

### 네비게이션

```
Sidebar
├─ 빠른 추출 시작 → /quick-extraction
├─ 문서 추출 (그룹)
│   ├─ 모델 A → /models/{modelA_id}
│   ├─ 모델 B → /models/{modelB_id}
│   └─ ...
├─ 모델 관리 (그룹)
│   ├─ 모델 스튜디오 → /admin/model-studio
│   └─ 모델 갤러리 → /models
├─ 시스템 설정 (그룹)
│   ├─ 대시보드 → /admin/dashboard
│   ├─ 활동 로그 → /admin/audit
│   ├─ 일반 설정 → /admin/settings
│   └─ 사용자 관리 → /admin/users
└─ 전체 추출 기록 → /history
```

---

## 4. 라우팅 매핑

| URL Pattern | 컴포넌트 | 비고 |
|-------------|----------|------|
| `/models` | `ModelGallery` | 모델 갤러리 (landing) |
| `/models/:modelId` | `ModelView` → `DocumentExtractionView` | 모델별 추출 |
| `/models/:modelId/extractions/:logId` | `ModelView` (deep link) | 기록 열기 |
| `/extractions/:jobId` | `ModelView` | Job 직접 열기 |
| `/quick-extraction` | `QuickExtractionView` | 빠른 추출 |
| `/history` | `HistoryView` | 전체 기록 |
| `/admin/model-studio` | `ModelStudio` | 모델 관리 |
| `/admin/dashboard` | `AdminDashboard` | 관리자 대시보드 |

> **주의:** `/models/:modelId` 간 전환 시 `key={modelId}` 로 컴포넌트 리마운트 필요 (같은 컴포넌트 재사용 방지)

---

## 5. 주요 파일 위치

### Frontend 핵심 파일

| 파일 | 역할 |
|------|------|
| `src/App.tsx` | 라우팅, 레이아웃, 사이드바 접기 상태 |
| `src/components/Sidebar.tsx` | 네비게이션 |
| `src/features/verification/context/ExtractionContext.tsx` | 추출 상태 관리 (폴링, reset) |
| `src/features/verification/components/DocumentExtractionView.tsx` | 진입점 (`key={modelId}`) |
| `src/features/verification/components/ExtractionReviewView.tsx` | 결과 표시 (preview + data) |
| `src/features/verification/components/PDFViewer.tsx` | PDF + 표 렌더링 |
| `src/features/verification/components/DataReviewPanel.tsx` | 데이터 편집 + Beta 탭 |
| `src/features/verification/constants/status.ts` | Status 상수 (`S100`, `P100` 등) |
| `src/features/verification/types.ts` | TypeScript 타입 정의 |
| `src/lib/api.ts` | API 클라이언트 (axios) |

### Backend 핵심 파일

| 파일 | 역할 |
|------|------|
| `app/api/endpoints/extraction_preview.py` | 추출 API 엔드포인트 (27개 함수) |
| `app/services/extraction_service.py` | 추출 파이프라인 핵심 (57KB) |
| `app/services/extraction_jobs.py` | Job CRUD (Cosmos DB) |
| `app/services/extraction_logs.py` | 추출 기록 관리 |
| `app/services/llm.py` | Azure OpenAI 호출 |
| `app/services/doc_intel.py` | Document Intelligence 호출 |
| `app/services/layout_parser.py` | Beta: LayoutParser (문서 구조 분석) |
| `app/services/prompt_service.py` | 프롬프트 관리 |
| `app/services/refiner.py` | 재추출 (Refine) |
| `app/core/enums.py` | Status enum (`ExtractionStatus`) |
