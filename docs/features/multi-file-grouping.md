# Multi-File Grouping (Feature Proposal)

**Status**: 검토중 (2026-02-07)  
**Priority**: 추출 안정화 이후 진행

## 개요
여러 파일을 하나의 "건"으로 묶어 관리하고, 필요시 통합분석하는 기능.

## 핵심 결정사항
- 파일 업로드는 **기존 원바이원 방식 유지** (새 업로드 기능 불필요)
- 추출 완료된 결과를 **체크박스로 선택 → 그룹으로 묶기**
- `group_id`로 연결, 별도 추출 재실행 없음
- 통합분석은 선택된 N개 결과를 LLM에 한번에 전달 (cross-reference)

## 필요한 변경

### Backend
- `extraction_log`에 `group_id: Optional[str]` 필드 추가
- `PATCH /extraction/logs/group` — 선택된 log_id들에 group_id 태깅
- `POST /extraction/analyze-group/{group_id}` — 통합분석 (옵션)

### Frontend
1. **이력 목록**: 체크박스 추가 + "그룹으로 묶기" 버튼
2. **이력 표시**: 그룹은 accordion으로 접이식 표시
3. **그룹 상세 뷰**: 탭 전환형 (파일별 탭 + 통합 탭)
   - 각 탭: 기존 뷰어 + 추출결과 그대로
   - 통합 탭: 파일별 추출결과를 열(column)로 나열한 비교 테이블

## 추가 검토 (초기 멀티파일 업로드)
- 드랍존에서 여러 파일 동시 선택 → 각각 개별 추출 + 자동 group_id 부여
- 백엔드 `start-job`이 이미 `List[UploadFile]` 지원하므로 인프라 있음
- Beta feature로 추가 가능

## 참고
- "합쳐서 추출" vs "개별추출 후 엮기" → **개별추출 후 엮기(B안) 우선**
- 합쳐서 추출은 토큰 리스크 있어 "Deep Context" Beta로 나중에 추가
