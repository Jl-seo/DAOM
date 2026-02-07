# DAOM 플랫폼 아키텍처 개요

> Document Automation & Orchestration Management - 문서 자동 추출 플랫폼

---

## 🏗️ 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        사용자 (브라우저)                          │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend (React + Vite)                       │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐    │
│  │ Sidebar │  │ Model   │  │ PDF     │  │ Extraction      │    │
│  │         │  │ Studio  │  │ Viewer  │  │ Review          │    │
│  └─────────┘  └─────────┘  └─────────┘  └─────────────────┘    │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI)                             │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐    │
│  │ Documents │  │ Models    │  │ Settings  │  │ Groups    │    │
│  │ API       │  │ API       │  │ API       │  │ API       │    │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘    │
│        └──────────────┴──────────────┴──────────────┘           │
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    Services Layer                        │    │
│  │  extraction_service │ doc_intel │ llm │ prompt_service  │    │
│  └─────────────────────────────────────────────────────────┘    │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Azure 서비스                                  │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐    │
│  │ Cosmos DB │  │ Blob      │  │ Document  │  │ Azure     │    │
│  │           │  │ Storage   │  │ Intel     │  │ OpenAI    │    │
│  │ (데이터)   │  │ (파일)    │  │ (OCR)     │  │ (LLM)     │    │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 데이터 흐름

### 문서 추출 프로세스

```
1. 문서 업로드
   └→ Blob Storage에 저장
   └→ Document Intelligence로 OCR

2. LLM 추출
   └→ 모델 필드 정의 로드
   └→ 시스템 프롬프트 + OCR 데이터
   └→ Azure OpenAI 호출
   └→ JSON 결과 파싱

3. 결과 검토
   └→ PDF 뷰어에 하이라이팅
   └→ 수동 수정 가능
   └→ Cosmos DB에 저장
```

---

## 🔑 핵심 기능

| 기능 | 설명 |
|------|------|
| **모델 스튜디오** | 추출 필드 정의, 샘플 문서로 AI 자동 생성 |
| **실시간 추출** | 문서 업로드 → 즉시 추출 결과 표시 |
| **PDF 하이라이팅** | 추출된 값의 원문 위치 표시 |
| **배치 처리** | 여러 문서 일괄 추출 |
| **프롬프트 편집** | 어드민에서 LLM 프롬프트 커스터마이징 |
| **다국어 지원** | 한국어, 영어 UI |
| **권한 관리** | 그룹 기반 모델/메뉴 접근 제어 |
| **테마 커스터마이징** | 사이트 이름, 로고, 색상 변경 |

---

## 📚 문서 목차

| 문서 | 설명 |
|------|------|
| [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) | 설치 가이드 (Azure 리소스 생성 ~ 배포) |
| [backend_guide.md](./backend_guide.md) | 백엔드 API, 스키마, 서비스 설명 |
| [frontend_guide.md](./frontend_guide.md) | 프론트엔드 컴포넌트, 훅, 스타일 설명 |
| **운영 매뉴얼 (2026-02 신규)** | |
| [extraction-pipeline.md](./dataflow/extraction-pipeline.md) | 추출 파이프라인 데이터 플로우 (함수 + 스키마 수준) |
| [frontend-components.md](./dataflow/frontend-components.md) | 컴포넌트 트리, 상태 관리, 라우팅 매핑 |
| [api-contracts.md](./dataflow/api-contracts.md) | API 엔드포인트 & 요청/응답 스키마 |
| [troubleshooting.md](./dataflow/troubleshooting.md) | 자주 발생하는 버그 패턴 & 해결법 |

---

## 🛠️ 기술 스택

### Backend
- **Framework**: FastAPI (Python 3.11+)
- **Database**: Azure Cosmos DB (NoSQL)
- **Storage**: Azure Blob Storage
- **AI/ML**: Azure Document Intelligence, Azure OpenAI

### Frontend
- **Framework**: React 18 + TypeScript
- **Build**: Vite 7
- **Styling**: Tailwind CSS
- **UI Components**: shadcn/ui
- **State**: React Context + React Query

### Infrastructure
- **Hosting**: Azure Container Apps
- **Registry**: Azure Container Registry
- **Auth**: Microsoft Entra ID (선택)

---

## 🔄 버전 정보

| 구성 요소 | 버전 |
|----------|------|
| FastAPI | 0.100+ |
| React | 18.x |
| Vite | 7.x |
| Python | 3.11+ |
| Node.js | 18+ |

---

## 📞 지원

- **기술 문의**: support@example.com
- **소스 코드**: https://github.com/Jl-seo/DAOM
