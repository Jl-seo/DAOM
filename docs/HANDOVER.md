# 📚 DAOM 개발자 핸드오버 매뉴얼

> **Document Automation & Optimization Manager (DAOM)** 플랫폼의 개발자 온보딩 및 인수인계를 위한 종합 가이드입니다.

---

## 📋 목차

| # | 문서 | 설명 |
|---|------|------|
| 1 | [시작하기](handover/01-getting-started.md) | 로컬 환경 설정, 실행, 검증 |
| 2 | [시스템 아키텍처](handover/02-architecture.md) | 전체 시스템 구조, Azure 서비스, 데이터 흐름 |
| 3 | [백엔드 가이드](handover/03-backend.md) | FastAPI 구조, 서비스 레이어, DB, 설정 체계 |
| 4 | [프론트엔드 가이드](handover/04-frontend.md) | React 구조, 라우팅, 상태관리, UI 컴포넌트 |
| 5 | [추출 파이프라인](handover/05-extraction-pipeline.md) | 문서 추출의 전체 흐름 (OCR → LLM → 후처리) |
| 6 | [관리자 기능](handover/06-admin-features.md) | 모델 관리, 사용자/그룹, RBAC, 감사 로그 |
| 7 | [배포 가이드](handover/07-deployment.md) | CI/CD, Docker, Azure Container Apps |
| 8 | [트러블슈팅](handover/08-troubleshooting.md) | 자주 발생하는 문제와 해결 방법 |
| 9 | [용어집](handover/09-glossary.md) | 주요 용어, 상태 코드, 코드 관례 |

---

## 🏗️ 기존 문서 참조

| 문서 | 설명 |
|------|------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 아키텍처 다이어그램, 핵심 기능, 로드맵 (한국어) |
| [SYSTEM.md](SYSTEM.md) | 전체 시스템 상세 명세 (한국어) |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Azure 리소스 설정 및 배포 (한국어) |
| [SCHEMA_GUIDE.md](SCHEMA_GUIDE.md) | 스키마 레퍼런스 |
| [dataflow/](dataflow/) | 데이터 플로우 상세 문서 (추출, API 계약, 트러블슈팅) |

---

## 🚀 빠른 시작

```bash
# 1. 저장소 클론
git clone <repository-url>
cd daom

# 2. 백엔드 실행
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 환경변수 편집
uvicorn main:app --reload --port 8000

# 3. 프론트엔드 실행 (새 터미널)
cd frontend
npm install
cp .env.example .env  # 환경변수 편집
npm run dev
```

> 자세한 내용은 [01. 시작하기](handover/01-getting-started.md)를 참조하세요.

---

## 🔑 핵심 기술 스택

| 레이어 | 기술 |
|--------|------|
| **프론트엔드** | React 19 + Vite 7 + TypeScript 5.9 + Tailwind CSS 4 |
| **백엔드** | FastAPI 0.128 + Python 3.12 + Pydantic 2 |
| **데이터베이스** | Azure Cosmos DB (NoSQL) |
| **AI/OCR** | Azure Document Intelligence + Azure AI Foundry (OpenAI) |
| **인증** | Microsoft Entra ID (MSAL) |
| **파일 저장소** | Azure Blob Storage |
| **배포** | Azure Container Apps + GitHub Actions + GHCR |

---

*최종 업데이트: 2026-02-09*
