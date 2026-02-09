# 8. 트러블슈팅

> 개발 및 운영 중 자주 발생하는 문제와 해결 방법을 정리합니다.

---

## 🔴 추출 관련 문제

### 1. 추출 결과가 비어있음 (`{}`)

**증상**: 추출 완료 후 `extracted_data`가 빈 객체

**원인 및 해결**:

| 원인 | 해결 |
|------|------|
| OCR 결과가 비어있음 | Document Intelligence 키/엔드포인트 확인, 문서 형식 지원 여부 확인 |
| LLM 토큰 초과 | `LLM_MAX_TOKENS` 증가 또는 청킹 설정 조정 |
| 프롬프트 오류 | debug_data에서 `prompt_sent` 확인 |
| JSON 파싱 실패 | LLM 응답이 유효한 JSON이 아닐 수 있음 → `raw_response` 확인 |

### 2. 추출 결과가 일부만 나옴 (행 누락)

**증상**: 대용량 문서에서 처음 5~10행만 추출되고 나머지 누락

**원인**: 텍스트 청킹 시 후속 청크에 테이블 헤더 정보 부재

**해결**: Header Context Injection이 동작하는지 확인:
```python
# beta_pipeline.py 에서 확인
header_context = full_content[:800]  # 첫 800자 헤더

if chunk_idx > 0:
    final_chunk = header_context + "\n... [Header Context End] ...\n" + chunk_text
```

### 3. 필드 키가 번역됨

**증상**: `premium_rate` 대신 `프리미엄_요율`로 반환

**원인**: LLM이 필드 키를 한국어로 번역

**해결**: 프롬프트에 필드 키 유지 지시 추가:
```
중요: JSON 키는 반드시 다음 영어 원본을 유지하세요: premium_rate, age_group, rate
절대로 키를 번역하지 마세요.
```

### 4. Dict-as-List 변환 안됨

**증상**: 테이블 데이터가 `{"0": {...}, "1": {...}}` 형태로 반환

**확인**: 후처리 로직에서 Dict-as-List 정규화 동작 확인:
```python
# 이 패턴이 자동 변환되어야 함
{"0": {"name": "A"}, "1": {"name": "B"}}  →  [{"name": "A"}, {"name": "B"}]
```

### 5. PDF 하이라이팅이 안 나옴

**증상**: 추출 결과는 있지만 PDF에서 하이라이팅 표시 안됨

**점검 순서**:
1. `extracted_data`에 바운딩 박스 좌표가 포함되어 있는지 확인
2. `ExtractionContext`에서 하이라이트 데이터가 전달되는지 확인
3. PDF 뷰어가 `@react-pdf-viewer/highlight` 플러그인을 사용하는지 확인
4. `fileId`가 멀티 문서인 경우 올바르게 매핑되는지 확인

### 6. 엑셀 추출 시 데이터 잘림

**증상**: 엑셀 파일에서 일부 시트/행만 추출

**원인**: 토큰 제한으로 전체 엑셀 데이터 전송 불가

**해결**: 
- `CHUNK_SIZE` 증가
- `beta_features.use_virtual_excel_ocr` 활성화
- 3-Tier 청킹 전략 확인

---

## 🟡 프론트엔드 문제

### 1. TypeScript 빌드 실패

```
error TS6133: 'someVar' is declared but its value is never read.
error TS6196: 'SomeType' is declared but never used.
```

**해결**: 사용하지 않는 변수/타입/import를 제거합니다:
```diff
-import { SomeUnusedType } from './types';
-const unusedVar = 'test';
```

### 2. verbatimModuleSyntax 에러

```
error TS1484: 'SomeType' is a type and must be imported using a type-only import
```

**해결**: 타입 import에 `type` 키워드 추가:
```diff
-import { SomeType } from './types';
+import type { SomeType } from './types';
```

### 3. CORS 에러

```
Access to XMLHttpRequest at 'http://localhost:8000/api/v1/...' has been blocked by CORS policy
```

**해결**: 백엔드 `.env`에서 CORS 설정 확인:
```env
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

### 4. MSAL 로그인 실패

**증상**: 로그인 리다이렉트 후 빈 화면 또는 에러

**점검**:
1. `VITE_AZURE_TENANT_ID` 환경변수 확인
2. `VITE_AZURE_CLIENT_ID` 확인
3. Entra ID 앱 등록에서 Redirect URI 확인 (`http://localhost:5173`)
4. 브라우저 콘솔에서 MSAL 에러 메시지 확인

### 5. 상태 동기화 문제 (URL ↔ 컴포넌트)

**증상**: URL 파라미터 변경해도 UI가 업데이트되지 않음, 또는 그 반대

**해결**: `useEffect` 의존성 배열 확인:
```tsx
// ✅ 올바름
useEffect(() => {
  const tab = searchParams.get('tab');
  setActiveTab(tab || 'fields');
}, [searchParams]);  // searchParams 의존성 포함

// ❌ 잘못됨 (빈 의존성 → 초기 한 번만 실행)
useEffect(() => { ... }, []);
```

---

## 🟠 백엔드 문제

### 1. import 에러

```
ModuleNotFoundError: No module named 'app.services.xxx'
```

**점검**:
```bash
# 5-Step Import Check
python -c "import app"                              # Step 1
python -c "from app.core.config import settings"    # Step 2
python -c "from app.db.cosmos import get_database"  # Step 3
python -c "from app.services.llm import call_llm"   # Step 4
python -c "from app.api.api import api_router"      # Step 5
```

**일반적 원인**:
- `__init__.py` 누락
- 순환 import
- `requirements.txt`에 새 패키지 미등록

### 2. Cosmos DB 연결 실패

```
[Cosmos] No credentials configured, using local JSON fallback
```

**해결**: `.env` 파일에서 확인:
```env
COSMOS_ENDPOINT=https://your-cosmos.documents.azure.com:443/
COSMOS_KEY=<primary-key>
COSMOS_DATABASE=daom
```

### 3. LLM 호출 실패/타임아웃

**점검 순서**:
1. `AI_FOUNDRY_ENDPOINT`와 `AI_FOUNDRY_KEY` 확인
2. `AI_FOUNDRY_DEPLOYMENT` (모델 배포 이름) 확인
3. Azure Portal에서 배포 상태 및 쿼터 확인
4. 네트워크 연결 확인

### 4. Rate Limiting 에러 (429)

```
{"detail": "Rate limit exceeded"}
```

**원인**: `slowapi` Rate limiting 발동

**해결**: 잠시 대기 후 재시도. 지속적이면 Rate limit 설정 확인

---

## 🔵 배포 문제

### 1. Docker 빌드 실패 (프론트엔드)

```
FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory
```

**해결**: `NODE_OPTIONS` 메모리 설정 확인:
```dockerfile
ENV NODE_OPTIONS="--max-old-space-size=4096"
```

### 2. Container Apps 배포 후 접속 불가

**점검**:
1. Container Apps 포탈에서 리비전 상태 확인 (Running/Failed)
2. 로그 확인: `az containerapp logs show --name daom-backend --resource-group Dalle2`
3. 환경변수 설정 확인 (Azure Portal → Container Apps → Settings → Environment variables)
4. Ingress 설정 확인 (포트, 트래픽 %)

### 3. GHCR 인증 실패

```
Error response from daemon: pull access denied for ghcr.io/...
```

**해결**: Container Apps 레지스트리 인증 갱신:
```bash
az containerapp registry set \
  --name daom-backend \
  --resource-group Dalle2 \
  --server ghcr.io \
  --username <github-user> \
  --password <github-token>
```

---

## 🔧 디버그 도구

### 1. Debug Modal (프론트엔드)

추출 결과 상세 화면에서 디버그 데이터 확인 가능:
- 실제 전송된 프롬프트
- LLM 원본 응답
- 처리 단계별 로그
- 토큰 사용량

### 2. Azure Portal 로그

```bash
# Container Apps 실시간 로그
az containerapp logs show \
  --name daom-backend \
  --resource-group Dalle2 \
  --follow

# 특정 리비전 로그
az containerapp logs show \
  --name daom-backend \
  --resource-group Dalle2 \
  --revision daom-backend--prod-12345
```

### 3. Swagger UI

로컬: `http://localhost:8000/docs`
프로덕션: `https://daom-backend.<env>.azurecontainerapps.io/docs`

→ API 직접 테스트 가능

---

**다음**: [09. 용어집](09-glossary.md)에서 주요 용어와 코드 관례를 확인합니다.
