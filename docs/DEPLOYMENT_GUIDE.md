# DAOM 플랫폼 설치 가이드

> 이 가이드는 Azure를 처음 사용하는 분도 따라할 수 있도록 상세하게 작성되었습니다.

---

## 목차
1. [준비물 확인](#1-준비물-확인)
2. [Azure Portal 접속](#2-azure-portal-접속)
3. [리소스 그룹 만들기](#3-리소스-그룹-만들기)
4. [Cosmos DB 만들기](#4-cosmos-db-만들기)
5. [저장소(Storage) 만들기](#5-저장소storage-만들기)
6. [AI Document Intelligence 만들기](#6-ai-document-intelligence-만들기)
7. [Azure OpenAI 만들기](#7-azure-openai-만들기)
8. [Container Apps 환경 만들기](#8-container-apps-환경-만들기)
9. [애플리케이션 배포하기](#9-애플리케이션-배포하기)
10. [최종 확인](#10-최종-확인)

---

## 1. 준비물 확인

시작하기 전에 아래 항목을 확인하세요:

✅ **Azure 계정**
- Azure Portal 로그인이 가능해야 합니다
- 구독(Subscription)이 활성화되어 있어야 합니다
- 결제 방법이 등록되어 있어야 합니다

✅ **권한 확인**
- 구독에서 "기여자(Contributor)" 이상의 권한이 필요합니다
- 권한이 없으면 IT 관리자에게 요청하세요

✅ **예상 비용** (월 기준)
| 구성 요소 | 예상 비용 |
|----------|----------|
| Cosmos DB (Serverless) | ~$5-20 |
| Blob Storage | ~$5-10 |
| Container Apps | ~$30-100 |
| Document Intelligence | ~$50-200 |
| Azure OpenAI | ~$50-200 |
| **합계** | **~$150-500/월** |

---

## 2. Azure Portal 접속

### 단계 2.1: 브라우저에서 Azure Portal 열기

1. 웹 브라우저를 엽니다 (Chrome, Edge 권장)
2. 주소창에 입력: **https://portal.azure.com**
3. Enter 키를 누릅니다

### 단계 2.2: 로그인

1. 회사 이메일 또는 Microsoft 계정으로 로그인
2. 2단계 인증이 있으면 진행

### 단계 2.3: 구독 확인

1. 왼쪽 메뉴에서 **구독(Subscriptions)** 클릭
2. 활성화된 구독이 있는지 확인
3. 없으면 IT 관리자에게 문의

---

## 3. 리소스 그룹 만들기

> **리소스 그룹이란?** DAOM에 필요한 모든 Azure 리소스를 하나로 묶어주는 폴더 같은 것입니다.

### 단계 3.1: 리소스 그룹 화면 열기

1. Azure Portal 상단의 검색창에 **리소스 그룹** 입력
2. **리소스 그룹** 클릭

### 단계 3.2: 새 리소스 그룹 만들기

1. **+ 만들기** 버튼 클릭
2. 다음 정보 입력:
   - **구독**: 사용할 구독 선택
   - **리소스 그룹 이름**: `rg-daom-prod`
   - **지역**: `Korea Central` (한국 중부)
3. **검토 + 만들기** 클릭
4. **만들기** 클릭

### 단계 3.3: 만들어졌는지 확인

1. 알림(종 모양 아이콘)에서 "배포 완료" 확인
2. 리소스 그룹 목록에서 `rg-daom-prod` 확인

---

## 4. Cosmos DB 만들기

> **Cosmos DB란?** DAOM의 모든 데이터(모델 정의, 추출 기록 등)를 저장하는 데이터베이스입니다.

### 단계 4.1: Cosmos DB 화면 열기

1. Azure Portal 검색창에 **Cosmos DB** 입력
2. **Azure Cosmos DB** 클릭

### 단계 4.2: 새 Cosmos DB 계정 만들기

1. **+ 만들기** 클릭
2. **Azure Cosmos DB for NoSQL** 선택 후 **만들기** 클릭

### 단계 4.3: 기본 정보 입력

다음 정보를 입력합니다:

| 항목 | 값 |
|------|-----|
| 구독 | 사용 중인 구독 |
| 리소스 그룹 | `rg-daom-prod` |
| 계정 이름 | `daom-cosmos-prod` (소문자만, 회사명 추가 가능) |
| 위치 | `Korea Central` |
| 용량 모드 | **서버리스(Serverless)** ← 중요! |

### 단계 4.4: 만들기 완료

1. **검토 + 만들기** 클릭
2. 유효성 검사 통과 확인
3. **만들기** 클릭
4. ⏱️ 약 5-10분 소요

### 단계 4.5: 연결 정보 복사하기 (중요!)

만들기 완료 후:

1. 생성된 Cosmos DB 계정으로 이동
2. 왼쪽 메뉴에서 **키(Keys)** 클릭
3. 다음 값을 복사해서 **메모장에 저장**:
   - **URI**: `https://daom-cosmos-prod.documents.azure.com:443/`
   - **기본 키(PRIMARY KEY)**: `AbCd1234...` (긴 문자열)

### 단계 4.6: 데이터베이스 만들기

1. 왼쪽 메뉴에서 **데이터 탐색기(Data Explorer)** 클릭
2. **새 데이터베이스(New Database)** 클릭
3. 데이터베이스 ID: `daom`
4. **확인** 클릭

---

## 5. 저장소(Storage) 만들기

> **Storage란?** 사용자가 업로드하는 PDF, 이미지 파일을 저장하는 곳입니다.

### 단계 5.1: 스토리지 계정 화면 열기

1. Azure Portal 검색창에 **스토리지 계정** 입력
2. **스토리지 계정** 클릭

### 단계 5.2: 새 스토리지 계정 만들기

1. **+ 만들기** 클릭
2. 다음 정보 입력:

| 항목 | 값 |
|------|-----|
| 구독 | 사용 중인 구독 |
| 리소스 그룹 | `rg-daom-prod` |
| 스토리지 계정 이름 | `daomstorageprod` (소문자, 숫자만, 3-24자) |
| 지역 | `Korea Central` |
| 성능 | **표준(Standard)** |
| 중복 | **LRS (로컬 중복)** |

3. **검토 + 만들기** 클릭
4. **만들기** 클릭

### 단계 5.3: 컨테이너 만들기

만들기 완료 후:

1. 생성된 스토리지 계정으로 이동
2. 왼쪽 메뉴에서 **컨테이너(Containers)** 클릭
3. **+ 컨테이너** 클릭
4. 이름: `documents`
5. 공용 액세스 수준: **프라이빗** (기본값)
6. **만들기** 클릭

### 단계 5.4: 연결 문자열 복사하기 (중요!)

1. 왼쪽 메뉴에서 **액세스 키(Access keys)** 클릭
2. **연결 문자열(Connection string)** 옆의 **표시** 클릭
3. 전체 문자열 복사해서 **메모장에 저장**

예시:
```
DefaultEndpointsProtocol=https;AccountName=daomstorageprod;AccountKey=abc123...;EndpointSuffix=core.windows.net
```

---

## 6. AI Document Intelligence 만들기

> **Document Intelligence란?** PDF와 이미지에서 텍스트를 추출하는 OCR 서비스입니다.

### 단계 6.1: AI 서비스 화면 열기

1. Azure Portal 검색창에 **Document Intelligence** 입력
2. **Azure AI Document Intelligence** 클릭

### 단계 6.2: 새 리소스 만들기

1. **+ 만들기** 클릭
2. 다음 정보 입력:

| 항목 | 값 |
|------|-----|
| 구독 | 사용 중인 구독 |
| 리소스 그룹 | `rg-daom-prod` |
| 지역 | `Korea Central` |
| 이름 | `daom-docintel-prod` |
| 가격 책정 계층 | **S0 표준** |

3. **검토 + 만들기** → **만들기**

### 단계 6.3: 키와 엔드포인트 복사하기 (중요!)

만들기 완료 후:

1. 생성된 리소스로 이동
2. 왼쪽 메뉴에서 **키 및 엔드포인트(Keys and Endpoint)** 클릭
3. 다음 값을 **메모장에 저장**:
   - **엔드포인트**: `https://daom-docintel-prod.cognitiveservices.azure.com/`
   - **키 1**: `1234abcd...`

---

## 7. Azure OpenAI 만들기

> **Azure OpenAI란?** GPT 모델을 사용해서 문서에서 데이터를 추출하는 AI 서비스입니다.

⚠️ **주의**: Azure OpenAI는 별도 신청이 필요할 수 있습니다. 
신청: https://aka.ms/oai/access

### 단계 7.1: Azure OpenAI 화면 열기

1. Azure Portal 검색창에 **Azure OpenAI** 입력
2. **Azure OpenAI** 클릭

### 단계 7.2: 새 리소스 만들기

1. **+ 만들기** 클릭
2. 다음 정보 입력:

| 항목 | 값 |
|------|-----|
| 구독 | 사용 중인 구독 |
| 리소스 그룹 | `rg-daom-prod` |
| 지역 | `East US` 또는 `Sweden Central` (한국은 제한됨) |
| 이름 | `daom-openai-prod` |
| 가격 책정 계층 | **Standard S0** |

3. **검토 + 만들기** → **만들기**

### 단계 7.3: GPT 모델 배포하기

**이 단계가 매우 중요합니다!**

1. 생성된 Azure OpenAI 리소스로 이동
2. **Azure OpenAI Studio로 이동** 버튼 클릭
3. 왼쪽 메뉴에서 **배포(Deployments)** 클릭
4. **+ 새 배포 만들기** 클릭
5. 다음 선택:
   - 모델: **gpt-4o** 또는 **gpt-4o-mini** (권장)
   - 배포 이름: `gpt-4o-mini` (정확히 기억!)
   - 버전: 최신 버전
6. **만들기** 클릭

### 단계 7.4: 키와 엔드포인트 복사하기 (중요!)

1. Azure Portal로 돌아가기
2. 생성된 Azure OpenAI 리소스에서 **키 및 엔드포인트** 클릭
3. 다음 값을 **메모장에 저장**:
   - **엔드포인트**: `https://daom-openai-prod.openai.azure.com/`
   - **키 1**: `9876zyxw...`
   - **배포 이름**: `gpt-4o-mini` (위에서 만든 이름)

---

## 8. Container Apps 환경 만들기

> **Container Apps란?** DAOM 애플리케이션을 실행하는 서버 환경입니다.

### 단계 8.1: Container Apps 환경 화면 열기

1. Azure Portal 검색창에 **Container Apps 환경** 입력
2. **Container Apps 환경** 클릭

### 단계 8.2: 새 환경 만들기

1. **+ 만들기** 클릭
2. 다음 정보 입력:

| 항목 | 값 |
|------|-----|
| 구독 | 사용 중인 구독 |
| 리소스 그룹 | `rg-daom-prod` |
| 환경 이름 | `daom-cae-prod` |
| 지역 | `Korea Central` |
| 영역 중복성 | **비활성화됨** (비용 절감) |

3. **검토 + 만들기** → **만들기**

### 단계 8.3: Container Registry 만들기

1. Azure Portal 검색창에 **컨테이너 레지스트리** 입력
2. **컨테이너 레지스트리** 클릭
3. **+ 만들기** 클릭
4. 정보 입력:

| 항목 | 값 |
|------|-----|
| 레지스트리 이름 | `daomcrprod` (소문자, 숫자만) |
| 리소스 그룹 | `rg-daom-prod` |
| 위치 | `Korea Central` |
| SKU | **기본(Basic)** |

5. **만들기** 클릭

### 단계 8.4: 관리자 액세스 활성화

1. 생성된 컨테이너 레지스트리로 이동
2. 왼쪽 메뉴에서 **액세스 키(Access keys)** 클릭
3. **관리자 사용자** 토글을 **활성화**로 변경
4. 다음 값을 **메모장에 저장**:
   - 로그인 서버: `daomcrprod.azurecr.io`
   - 사용자 이름: `daomcrprod`
   - 암호: `aBcDeFg...`

---

## 9. 애플리케이션 배포하기

### 단계 9.1: 소스 코드 받기

터미널(명령 프롬프트)에서:

```bash
git clone https://github.com/Jl-seo/DAOM.git
cd DAOM
```

### 단계 9.2: Backend 환경 설정 (.env 파일 만들기)

1. `backend` 폴더로 이동
2. `.env.example` 파일을 `.env`로 복사
3. 메모장에 저장해둔 값으로 수정:

```env
PROJECT_NAME=DAOM
BACKEND_CORS_ORIGINS=["https://daom-frontend.koreacentral.azurecontainerapps.io"]

# Cosmos DB (4단계에서 복사한 값)
COSMOS_ENDPOINT=https://daom-cosmos-prod.documents.azure.com:443/
COSMOS_KEY=여기에_Cosmos_기본키_붙여넣기
COSMOS_DATABASE=daom

# Document Intelligence (6단계에서 복사한 값)
AZURE_FORM_ENDPOINT=https://daom-docintel-prod.cognitiveservices.azure.com/
AZURE_FORM_KEY=여기에_Document_Intelligence_키_붙여넣기

# Azure OpenAI (7단계에서 복사한 값)
AZURE_OPENAI_ENDPOINT=https://daom-openai-prod.openai.azure.com/
AZURE_OPENAI_API_KEY=여기에_OpenAI_키_붙여넣기
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-05-01-preview

# Storage (5단계에서 복사한 값)
AZURE_STORAGE_CONNECTION_STRING=여기에_Storage_연결문자열_붙여넣기
AZURE_CONTAINER_NAME=documents
```

### 단계 9.3: Docker 이미지 빌드 및 푸시

⚠️ **Docker Desktop 설치 필요**: https://docker.com/products/docker-desktop

```bash
# Azure 로그인
az login

# Container Registry 로그인
az acr login --name daomcrprod

# Backend 빌드 & 푸시
cd backend
docker build -t daomcrprod.azurecr.io/daom-backend:latest .
docker push daomcrprod.azurecr.io/daom-backend:latest

# Frontend 빌드 & 푸시
cd ../frontend
docker build -t daomcrprod.azurecr.io/daom-frontend:latest .
docker push daomcrprod.azurecr.io/daom-frontend:latest
```

### 단계 9.4: Container App 생성 - Backend

Azure Portal에서:

1. **Container Apps** 검색 → 클릭
2. **+ 만들기** 클릭
3. 기본 정보:
   - 이름: `daom-backend`
   - 리소스 그룹: `rg-daom-prod`
   - 환경: `daom-cae-prod`
4. 컨테이너:
   - 이미지: `daomcrprod.azurecr.io/daom-backend:latest`
   - 레지스트리: `daomcrprod`
5. 수신:
   - 수신 트래픽: **모든 곳에서 트래픽 허용**
   - 대상 포트: `8000`
6. 환경 변수 추가 (9.2의 모든 값)
7. **만들기** 클릭

### 단계 9.5: Container App 생성 - Frontend

동일하게:
- 이름: `daom-frontend`
- 이미지: `daomcrprod.azurecr.io/daom-frontend:latest`
- 대상 포트: `80`

---

## 10. 최종 확인

### 단계 10.1: URL 확인

1. Container Apps 목록에서 `daom-frontend` 클릭
2. 개요에서 **애플리케이션 URL** 복사
3. 브라우저에서 접속

### 단계 10.2: 초기 설정

1. ⚙️ 관리자 설정 → LLM 모델 선택
2. 🎨 사이트 이름/로고 설정
3. 📄 모델 스튜디오에서 첫 추출 모델 생성
4. 📤 테스트 문서 업로드해서 추출 테스트

---

## 🆘 문제가 생겼어요!

| 증상 | 원인 | 해결 방법 |
|------|------|----------|
| 페이지가 안 열려요 | Container App 시작 안됨 | 로그 확인: Container Apps → 로그 스트림 |
| 500 오류 | Cosmos DB 연결 실패 | `.env`의 `COSMOS_KEY` 확인 |
| OCR이 안 돼요 | Document Intelligence 키 오류 | `AZURE_FORM_KEY` 확인 |
| 추출 결과가 비어있어요 | OpenAI 모델 미배포 | Azure OpenAI Studio에서 배포 확인 |
| 파일 업로드 실패 | Storage 연결 문자열 오류 | `AZURE_STORAGE_CONNECTION_STRING` 확인 |

---

## 📞 도움이 필요하면

- 기술 지원: support@example.com
- 긴급 연락: +82-10-XXXX-XXXX

**이 가이드를 완료하셨다면 DAOM 플랫폼 설치가 완료된 것입니다! 🎉**
