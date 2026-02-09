# 9. 용어집

> DAOM 플랫폼에서 사용되는 주요 용어, 상태 코드, 코드 관례를 정리합니다.

---

## 📖 핵심 용어

| 용어 | 설명 |
|------|------|
| **DAOM** | Document Automation & Optimization Manager. 문서 자동화 및 최적화 관리 플랫폼 |
| **IDP** | Intelligent Document Processing. 지능형 문서 처리 |
| **Brain** | 백엔드 레이어 (FastAPI). 비즈니스 로직과 API 처리 |
| **Face** | 프론트엔드 레이어 (React SPA). 사용자 인터페이스 |
| **Muscle** | Azure 서비스 레이어. 인프라 및 AI 서비스 |

---

## 🧠 추출 관련 용어

| 용어 | 설명 |
|------|------|
| **guide_extracted** | 추출 결과의 최상위 래퍼 키. 모든 추출 결과는 이 키 안에 포함됨 |
| **LayoutParser** | OCR 결과를 구조화된 텍스트(Index-Reference 형식)로 변환하는 모듈 |
| **Index-Reference** | 테이블에 인덱스(`TABLE_1`)를 부여하여 LLM이 참조할 수 있게 하는 패턴 |
| **Refiner** | 필드 정의, 전역 규칙, OCR 결과를 조합하여 LLM 프롬프트를 생성하는 모듈 |
| **3-Tier Chunking** | 문서 크기에 따라 페이지별/단일/텍스트 청킹을 선택하는 전략 |
| **Header Context Injection** | 텍스트 청킹 시 두 번째 이후 청크에 첫 800자 헤더를 주입하는 기법 |
| **Dict-as-List** | LLM이 `{"0": x, "1": y}` 형태로 반환한 데이터를 `[x, y]` 배열로 정규화 |
| **Beta Pipeline** | 실험적 기능이 포함된 추출 파이프라인 (`beta_pipeline.py`) |
| **RefMap** | Beta 추출에서 생성된 참조 매핑 데이터 (`_beta_ref_map`) |
| **Confidence Score** | 추출된 값의 신뢰도 점수 (0~1) |
| **bbox** | Bounding Box. OCR에서 인식된 텍스트/테이블의 좌표 영역 |

---

## 📊 상태 코드

### 추출 상태

| 상태 | 설명 |
|------|------|
| `pending` | 추출 요청됨, 처리 대기 중 |
| `processing` | 추출 처리 중 (OCR → LLM → 후처리) |
| `completed` | 추출 완료 |
| `failed` | 추출 실패 |

### 모델 상태

| 필드 | 값 | 설명 |
|------|-----|------|
| `is_active` | `true` | 활성 모델 (사이드바에 표시) |
| `is_active` | `false` | 비활성 모델 (숨김, soft delete) |

### 사용자 역할

| 역할 | 설명 |
|------|------|
| `admin` | 전체 관리 권한 |
| `manager` | 소속 그룹 관리 권한 |
| `user` | 일반 사용자 (추출 실행 가능) |
| `viewer` | 읽기 전용 |

---

## 🏗️ 아키텍처 패턴

| 패턴 | 설명 |
|------|------|
| **Infrastructure-as-Fallback** | DB 설정 > 모델 설정 > 환경변수 순서의 설정 우선순위 |
| **Service Delegation** | API 엔드포인트는 최소 로직만 포함하고, 비즈니스 로직은 Service 레이어에 위임 |
| **Tenant Isolation** | 모든 DB 쿼리에 `tenant_id`를 강제 주입하여 데이터 격리 |
| **Soft Delete** | 모델/사용자 삭제 시 `is_active: false`로 논리 삭제 |
| **Evidence Hub** | 추출 리뷰 UI에서 왼쪽(PDF/OCR) + 오른쪽(결과/편집) 분할 레이아웃 |
| **Route-to-State** | URL 파라미터와 컴포넌트 상태를 동기화하는 프론트엔드 패턴 |
| **Dual-Key Deep Linking** | `modelId + logId`로 추출 결과에 직접 접근하는 URL 체계 |
| **Library-First** | 복잡한 UI 로직을 재사용 가능한 라이브러리 컴포넌트로 캡슐화 |

---

## 📦 Azure 서비스 용어

| 용어 | 설명 |
|------|------|
| **Cosmos DB** | Azure NoSQL 데이터베이스. 파티션 키 기반 분산 저장소 |
| **Blob Storage** | Azure 객체 저장소. 문서 파일 저장 |
| **Document Intelligence** | Azure OCR/문서 분석 서비스 (이전 명칭: Form Recognizer) |
| **AI Foundry** | Azure OpenAI 서비스 호스팅 플랫폼 |
| **Entra ID** | Microsoft 통합 인증 서비스 (이전 명칭: Azure Active Directory) |
| **Container Apps** | Azure 컨테이너 호스팅 서비스 (Kubernetes 기반, 서버리스) |
| **MSAL** | Microsoft Authentication Library. 프론트엔드 인증 SDK |
| **GHCR** | GitHub Container Registry. Docker 이미지 저장소 |

---

## 🔑 환경변수 접두사

| 접두사 | 용도 | 예시 |
|--------|------|------|
| `COSMOS_` | Cosmos DB 연결 | `COSMOS_ENDPOINT`, `COSMOS_KEY` |
| `DOC_INTEL_` | Document Intelligence | `DOC_INTEL_ENDPOINT`, `DOC_INTEL_KEY` |
| `AI_FOUNDRY_` | Azure AI/OpenAI | `AI_FOUNDRY_ENDPOINT`, `AI_FOUNDRY_KEY` |
| `AZURE_STORAGE_` | Blob Storage | `AZURE_STORAGE_CONNECTION_STRING` |
| `AZURE_TENANT_` | Entra ID (백엔드) | `AZURE_TENANT_ID` |
| `AZURE_CLIENT_` | Entra ID (백엔드) | `AZURE_CLIENT_ID` |
| `VITE_` | 프론트엔드 환경변수 | `VITE_API_BASE_URL` |
| `LLM_` | LLM 파라미터 | `LLM_MAX_TOKENS`, `LLM_TEMPERATURE` |
| `CHUNK_` | 청킹 설정 | `CHUNK_SIZE`, `CHUNK_OVERLAP` |
| `CORS_` | CORS 설정 | `CORS_ORIGINS` |

---

## 📝 코드 관례

### 파일 명명

| 레이어 | 관례 | 예시 |
|--------|------|------|
| 백엔드 서비스 | `snake_case.py` | `extraction_service.py` |
| 백엔드 엔드포인트 | `snake_case.py` | `extraction_preview.py` |
| 프론트엔드 컴포넌트 | `PascalCase.tsx` | `ModelStudio.tsx` |
| 프론트엔드 유틸 | `camelCase.ts` | `formatDate.ts` |
| 번역 키 | `dot.notation` | `models.create`, `extraction.status.completed` |
| CSS 변수 | `--kebab-case` | `--primary`, `--background` |

### Import 순서 (프론트엔드)

```tsx
// 1. React/외부 라이브러리
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

// 2. 타입 (type import)
import type { Model } from '@/types/model';

// 3. 내부 컴포넌트
import { Button } from '@/components/ui/button';

// 4. 유틸/상수
import { formatDate } from '@/utils/date';
```

### 커밋 메시지

```
<type>(<scope>): <description>

feat(extraction): add Header Context Injection for text chunking
fix(frontend): resolve PDF highlighting regression
docs(handover): add backend guide
refactor(services): extract audit logging to separate service
```

| 타입 | 용도 |
|------|------|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `docs` | 문서 변경 |
| `refactor` | 리팩토링 (동작 변경 없음) |
| `style` | 스타일 변경 |
| `test` | 테스트 추가/수정 |
| `chore` | 빌드/설정 변경 |

---

## 📚 참고 문서

| 문서 | 위치 | 설명 |
|------|------|------|
| 시스템 아키텍처 | [ARCHITECTURE.md](../ARCHITECTURE.md) | 시스템 다이어그램, 기능 목록 |
| 상세 시스템 명세 | [SYSTEM.md](../SYSTEM.md) | 전체 시스템 상세 (610줄) |
| 배포 가이드 | [DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md) | Azure 리소스 설정 상세 |
| 데이터 플로우 | [dataflow/](../dataflow/) | 추출 파이프라인, API 계약, 트러블슈팅 |
| 핸드오버 목차 | [HANDOVER.md](../HANDOVER.md) | 이 매뉴얼의 메인 목차 |
