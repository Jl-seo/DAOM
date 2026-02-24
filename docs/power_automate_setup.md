# Power Automate Custom Connector 설정 가이드

DAOM 문서 추출 엔진을 Power Automate에서 사용하기 위한 Custom Connector 설정 가이드입니다.

## 사전 요구사항

- Azure AD (Entra ID) 테넌트
- DAOM 백엔드 배포 완료
- Power Automate 라이선스

---

## 1. Azure AD App Registration 설정

### 1.1 기존 DAOM 앱 재사용 (권장)

기존 DAOM App Registration에 API 권한을 추가합니다:

1. Azure Portal → App Registrations → DAOM 앱 선택
2. **Expose an API** 메뉴
3. **Add a scope** 클릭:
   - Scope name: `Extraction.ReadWrite`
   - Who can consent: Admins and users
   - Display name: `DAOM 문서 추출`
   - Description: `문서 업로드 및 추출 결과 조회`

### 1.2 Redirect URI 추가

Authentication → Add a platform → Web:
```
https://global.consent.azure-apim.net/redirect
```

---

## 2. Custom Connector 생성

### 2.1 Power Automate에서 생성

1. Power Automate → **Data** → **Custom connectors**
2. **+ New custom connector** → **Import an OpenAPI file**
3. `openapi_connector.yaml` 업로드

### 2.2 인증 설정

Security 탭에서:
- Authentication type: `OAuth 2.0`
- Identity Provider: `Azure Active Directory`
- Client ID: `{DAOM App Client ID}`
- Client Secret: `{DAOM App Secret}`
- Tenant ID: `{Your Tenant ID}`
- Resource URL: `api://{DAOM App Client ID}`

### 2.3 테스트

1. **Create connector** 클릭
2. Test 탭에서 **New connection** 생성
3. `ListModels` 액션 테스트

---

## 3. Power Automate Flow 예제

### 3.1 단건: SharePoint 파일 → DAOM 추출 → Excel 저장

```
트리거: When a file is created in a folder (SharePoint)
    ↓
액션 1: Get file content (SharePoint)
    ↓
액션 2: DAOM - UploadDocument
    - file: File Content
    - model_id: "invoice-model-id"
    - metadata: {"source": "SharePoint", "folder": triggerBody()?['Path']}
    ↓
액션 3: DAOM - WaitForExtraction
    - job_id: outputs('UploadDocument')?['body/job_id']
    ↓
액션 4: Add row to Excel (OneDrive)
    - Table: "Extractions"
    - Invoice Number: body('WaitForExtraction')?['extracted_data/invoice_number']
    - Amount: body('WaitForExtraction')?['extracted_data/total_amount']
```

### 3.2 다건 필터 조회: 어제 처리된 추출 결과 모조리 가져오기 (배치/루프 처리)

```
트리거: Recurrence (매일 아침 9시 실행)
    ↓
액션 1: DAOM - ListExtractions
    - model_id: "invoice-model-id"
    - status: "success"
    - start_date: "2026-02-23T00:00:00Z" (어제 시작일)
    - end_date: "2026-02-23T23:59:59Z" (어제 종료일)
    
    ⚠️ 필수 설정 (Pagination): 
    ListExtractions 우측 상단 '...' 클릭 -> Settings(설정) 메뉴 
    -> 'Pagination(페이지 매김)' 켜기 -> Threshold(임계값)을 5000으로 설정
    ↓
액션 2: Apply to each (루프)
    - 입력 배열: outputs('ListExtractions')?['body/results']
    ↓
액션 3 (루프 내부): Add row to Excel
    - Invoice Number: item()?['extracted_data']?['invoice_number']
```

---

## 4. 메타데이터 활용

### 요청 시 메타데이터 전달
```json
{
  "metadata": {
    "source": "Power Automate",
    "workflow_id": "flow-123",
    "document_id": "doc-456",
    "requester_email": "user@company.com"
  }
}
```

### 응답에서 메타데이터 사용
```
body('GetExtractionResult')?['metadata/document_id']
```

메타데이터는 DAOM에서 그대로 보존하여 응답에 포함됩니다.

---

## 5. 에러 처리

### 흔한 에러 및 해결

| 에러 | 원인 | 해결 |
|------|------|------|
| 401 Unauthorized | 토큰 만료 | Connection 재생성 |
| 403 Forbidden | 모델 권한 없음 | 그룹 권한 확인 |
| 404 Not Found | 잘못된 Job ID | job_id 값 확인 |
| 500 Internal Error | 서버 오류 | 로그 확인 |

### Retry 설정

Power Automate에서 자동 재시도 설정:
- Settings → Retry Policy → Fixed interval
- Count: 3, Interval: PT30S

---

## 6. 엔드포인트 요약

| 액션 | 메서드 | 경로 | 기능 설명 |
|------|--------|------|------|
| 📄 UploadDocument | POST | `/api/v1/connectors/upload` | 단일 파일 업로드 및 추출 |
| 📚 BatchUpload | POST | `/api/v1/connectors/batch-upload` | 다중 파일 일괄 업로드 |
| 🔍 GetExtractionResult | GET | `/api/v1/connectors/result/{job_id}` | 단일 결과 조회 |
| ⏳ WaitForExtraction | GET | `/api/v1/connectors/wait/{job_id}` | 완료될 때까지 대기 (폴링) |
| 📋 ListModels | GET | `/api/v1/connectors/models` | 사용 가능한 모델 목록 |
| ❌ CancelExtraction | POST | `/api/v1/connectors/cancel/{job_id}` | 추출 취소 |
| 📊 ListExtractions | GET | `/api/v1/connectors/results` | 조건(날짜/상태)에 맞는 결과 리스트 조회 |
