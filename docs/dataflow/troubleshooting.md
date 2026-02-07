# DAOM 트러블슈팅 가이드

> 이전 디버깅 경험에서 축적된 문제 패턴 → 원인 → 해결법 정리

---

## 디버깅 체크리스트 (빠른 참조)

| 증상 | 먼저 확인할 곳 | 관련 문서 |
|------|---------------|----------|
| 데이터가 null/0% | Backend `update_job()` → `extracted_data` 저장 여부 | [extraction-pipeline.md] |
| 표 제목만 보이고 내용 없음 | `PDFViewer.tsx` → `rowCount`/`columnCount` fallback | [frontend-components.md] |
| Beta 탭 안보임 | 모델 `beta_features` + `_beta_parsed_content` 존재 | [extraction-pipeline.md §2.4] |
| 사이드바 클릭해도 화면 안바뀜 | `DocumentExtractionView` → `key={modelId}` | [frontend-components.md §4] |
| 폴링 안멈춤 | `ExtractionContext` → status 비교 상수 (`S100`) | [extraction-pipeline.md §3.2] |
| 하이라이트 위치 이상 | `bbox.page` 누락 → 모두 1페이지에 표시 | 아래 §4 |
| LLM이 전부 "값을 찾지 못함" | 시스템 프롬프트 vs OCR 데이터 매칭 | 아래 §5 |

---

## 1. 추출 데이터 null 문제

### 증상
- 추출 완료인데 모든 필드가 빈 값 또는 0%
- `preview_data`는 있지만 `extracted_data`가 null

### 원인
`extraction_service.py` → `run_extraction_pipeline()` 에서 `update_job()` 호출 시 `extracted_data` 파라미터를 빼먹음

### 해결법
```python
# extraction_service.py → run_extraction_pipeline()
# guide_extracted를 평탄화해서 extracted_data로 저장
flat_extracted = {}
if sub_documents and sub_documents[0].get("data", {}).get("guide_extracted"):
    flat_extracted = sub_documents[0]["data"]["guide_extracted"]

extraction_jobs.update_job(
    job_id=job_id,
    status=ExtractionStatus.SUCCESS.value,
    preview_data=preview_payload,
    extracted_data=flat_extracted  # ← 이거 빠지면 안됨
)
```

### 점검 순서
1. Backend 로그에서 `update_job` 호출 확인
2. GET `/extraction/job/{job_id}` 응답에서 `extracted_data` 필드 확인
3. Frontend `ExtractionContext.tsx` 폴링 콜백에서 `data.extracted_data` 참조 확인

---

## 2. 표 데이터 렌더링 오류

### 증상
- "표 1", "표 2" 제목은 보이지만 표 내용이 비어있음
- `(N행 × M열)` 표시 안됨

### 원인
Document Intelligence가 `rowCount`/`columnCount` 없이 `cells`만 반환하는 경우 있음.
`PDFViewer.tsx`에서 `rowCount || 0` → grid 크기 0 → 빈 배열

### 해결법
```typescript
// PDFViewer.tsx — cells에서 dimensions 계산
const maxRow = table.cells.reduce((max, cell) => 
    Math.max(max, (cell.rowIndex || 0) + (cell.rowSpan || 1)), 0)
const maxCol = table.cells.reduce((max, cell) => 
    Math.max(max, (cell.columnIndex || 0) + (cell.columnSpan || 1)), 0)
const rowCount = table.rowCount || maxRow
const colCount = table.columnCount || maxCol
```

---

## 3. React Router 네비게이션 문제

### 증상
- 사이드바에서 다른 모델 클릭 → URL 변경됨 → 화면은 이전 모델 그대로

### 원인
같은 라우트(`/models/:modelId`)에서 파라미터만 바뀌면 React Router가 컴포넌트를 재사용함.
`ExtractionProvider`의 내부 state가 리셋되지 않음.

### 해결법
```tsx
// DocumentExtractionView.tsx
<ExtractionProvider key={props.modelId} ...>
```
`key` prop이 바뀌면 React가 전체 subtree를 unmount → remount 함.

### 비슷한 패턴 주의
- `/models/:modelId/extractions/:logId` → logId 변경 시에도 같은 문제 가능
- 필요시 `key={modelId + '-' + logId}` 로 확장

---

## 4. PDF 하이라이트 위치 오류

### 증상
- 2페이지 이후의 값이 모두 1페이지에 하이라이팅됨

### 원인
Backend에서 `bbox.page` 필드가 누락되면 Frontend가 기본값 1로 처리

### 점검
1. Backend `llm.py` → LLM 응답에서 `bbox.page` 포함 여부 확인
2. Frontend `ExtractionContext.tsx` → `highlights` 생성 로직에서 page 매핑 확인
3. `PDFViewer.tsx` → highlight 필터링이 `page === currentPage` 인지 확인

---

## 5. LLM 추출 실패 (전부 "값을 찾지 못함")

### 증상
- OCR은 성공 (raw_content 있음)
- LLM 응답은 모든 필드가 null 또는 "값을 찾지 못함"

### 원인들
1. **시스템 프롬프트 불일치**: 모델 필드 정의와 프롬프트가 안 맞음
2. **OCR 텍스트 품질 불량**: 스캔 품질이 낮으면 OCR이 깨진 텍스트 생성
3. **토큰 제한 초과**: 문서가 길면 잘림

### 디버깅
1. Backend 로그에서 `[LLM]` 프리픽스 로그 확인
2. `extraction_preview.py` → `get_preview_with_guide()` 에서 debug_data 반환 확인
3. Frontend 디버그 모달 (`DebugInfoModal.tsx`) 에서 프롬프트/응답 확인

---

## 6. Status 코드 불일치

### 주의사항
Backend와 Frontend에서 같은 Status를 다른 값으로 참조하면 폴링이 영원히 돌거나, 결과가 표시 안됨.

### 정확한 Status 매핑

| Backend Enum | 값 | Frontend 상수 | 용도 |
|-------------|-----|--------------|------|
| `ExtractionStatus.PROCESSING` | `"P100"` | `EXTRACTION_STATUS.PROCESSING` | 처리 시작 |
| `ExtractionStatus.ANALYZING` | `"P200"` | `EXTRACTION_STATUS.ANALYZING` | OCR 완료, LLM 진행 |
| `ExtractionStatus.SUCCESS` | `"S100"` | `EXTRACTION_STATUS.SUCCESS` | 성공 |
| `ExtractionStatus.ERROR` | `"E100"` | `EXTRACTION_STATUS.ERROR` | 실패 |

### Backend 위치
- `app/core/enums.py` → `ExtractionStatus` enum

### Frontend 위치
- `src/features/verification/constants/status.ts` → `EXTRACTION_STATUS` 객체
