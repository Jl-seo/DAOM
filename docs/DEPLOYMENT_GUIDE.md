# DAOM 배포 가이드

> 고객 Azure 테넌트에 DAOM 플랫폼을 설치하는 가이드입니다.

---

## 📋 사전 요구사항

### Azure 리소스
| 리소스 | SKU/Tier | 용도 |
|--------|----------|------|
| **Cosmos DB** | Serverless | 데이터 저장 |
| **Blob Storage** | Standard | 문서 파일 저장 |
| **Container Apps** | Consumption | Backend + Frontend 호스팅 |
| **AI Document Intelligence** | S0 | OCR 처리 |
| **Azure OpenAI** | Standard | LLM 추출 |
| **Entra ID** (선택) | - | 인증 |

### 예상 월 비용
| 규모 | 예상 비용 |
|------|----------|
| 소규모 (월 1,000건) | ~ $100-200 |
| 중규모 (월 10,000건) | ~ $300-500 |
| 대규모 (월 100,000건) | ~ $1,000+ |

---

## 🚀 1단계: Azure 리소스 생성

### 1.1 리소스 그룹 생성
```bash
az group create --name rg-daom-prod --location koreacentral
```

### 1.2 Cosmos DB 생성
```bash
az cosmosdb create \
  --name daom-cosmos-prod \
  --resource-group rg-daom-prod \
  --locations regionName=koreacentral \
  --capabilities EnableServerless

# 데이터베이스 생성
az cosmosdb sql database create \
  --account-name daom-cosmos-prod \
  --resource-group rg-daom-prod \
  --name daom
```

### 1.3 Blob Storage 생성
```bash
az storage account create \
  --name daomstorageprod \
  --resource-group rg-daom-prod \
  --location koreacentral \
  --sku Standard_LRS

az storage container create \
  --name documents \
  --account-name daomstorageprod
```

### 1.4 AI Document Intelligence 생성
```bash
az cognitiveservices account create \
  --name daom-docintel-prod \
  --resource-group rg-daom-prod \
  --kind FormRecognizer \
  --sku S0 \
  --location koreacentral
```

### 1.5 Azure OpenAI 생성 및 모델 배포
```bash
# Azure Portal에서 생성 후 GPT-4o 또는 GPT-4.1 모델 배포
# Deployment 이름 예: gpt-4o-mini
```

### 1.6 Container Apps 환경 생성
```bash
az containerapp env create \
  --name daom-cae-prod \
  --resource-group rg-daom-prod \
  --location koreacentral
```

---

## 🔧 2단계: 환경 변수 설정

### Backend (.env)
```env
# 기본 설정
PROJECT_NAME=DAOM
BACKEND_CORS_ORIGINS=["https://frontend-url.azurecontainerapps.io"]

# Cosmos DB
COSMOS_ENDPOINT=https://daom-cosmos-prod.documents.azure.com:443/
COSMOS_KEY=<your-cosmos-key>
COSMOS_DATABASE=daom

# AI Document Intelligence (OCR)
AZURE_FORM_ENDPOINT=https://daom-docintel-prod.cognitiveservices.azure.com/
AZURE_FORM_KEY=<your-form-key>

# Azure OpenAI (LLM)
AZURE_OPENAI_ENDPOINT=https://your-openai.openai.azure.com/
AZURE_OPENAI_API_KEY=<your-openai-key>
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-05-01-preview

# Blob Storage
AZURE_STORAGE_CONNECTION_STRING=<your-storage-connection-string>
AZURE_CONTAINER_NAME=documents
```

### Frontend (빌드 시)
```env
VITE_API_URL=https://backend-url.azurecontainerapps.io/api/v1
```

---

## 📦 3단계: 애플리케이션 배포

### 3.1 Container Registry 생성
```bash
az acr create \
  --name daomcrprod \
  --resource-group rg-daom-prod \
  --sku Basic \
  --admin-enabled true
```

### 3.2 Backend 이미지 빌드 & 푸시
```bash
cd backend
docker build -t daomcrprod.azurecr.io/daom-backend:latest .
az acr login --name daomcrprod
docker push daomcrprod.azurecr.io/daom-backend:latest
```

### 3.3 Backend Container App 생성
```bash
az containerapp create \
  --name daom-backend \
  --resource-group rg-daom-prod \
  --environment daom-cae-prod \
  --image daomcrprod.azurecr.io/daom-backend:latest \
  --target-port 8000 \
  --ingress external \
  --env-vars PROJECT_NAME=DAOM \
             COSMOS_ENDPOINT=... \
             # (기타 환경 변수)
```

### 3.4 Frontend 이미지 빌드 & 푸시
```bash
cd frontend
docker build -t daomcrprod.azurecr.io/daom-frontend:latest .
docker push daomcrprod.azurecr.io/daom-frontend:latest
```

### 3.5 Frontend Container App 생성
```bash
az containerapp create \
  --name daom-frontend \
  --resource-group rg-daom-prod \
  --environment daom-cae-prod \
  --image daomcrprod.azurecr.io/daom-frontend:latest \
  --target-port 80 \
  --ingress external
```

---

## ✅ 4단계: 확인 및 설정

### 4.1 URL 확인
```bash
# Backend URL
az containerapp show --name daom-backend --resource-group rg-daom-prod --query properties.configuration.ingress.fqdn -o tsv

# Frontend URL
az containerapp show --name daom-frontend --resource-group rg-daom-prod --query properties.configuration.ingress.fqdn -o tsv
```

### 4.2 초기 설정
1. Frontend URL 접속
2. 관리자 설정 → LLM 모델 선택
3. 관리자 설정 → 사이트 이름/로고 설정
4. 모델 스튜디오 → 첫 추출 모델 생성

---

## 🔒 보안 체크리스트

- [ ] CORS 설정에 프론트엔드 URL만 허용
- [ ] Cosmos DB 방화벽에서 Container Apps만 허용
- [ ] Storage Account에서 공용 액세스 비활성화
- [ ] 환경 변수에 민감 정보 Key Vault 연동 (권장)
- [ ] Entra ID 인증 설정 (권장)

---

## 🆘 문제 해결

| 증상 | 원인 | 해결 |
|------|------|------|
| 500 오류 | Cosmos 연결 실패 | COSMOS_ENDPOINT, COSMOS_KEY 확인 |
| OCR 실패 | Document Intelligence 키 오류 | AZURE_FORM_KEY 확인 |
| LLM 추출 안됨 | OpenAI 배포 없음 | Azure Portal에서 모델 배포 확인 |
| CORS 오류 | 허용 Origin 누락 | BACKEND_CORS_ORIGINS에 프론트 URL 추가 |

---

## 📞 지원 연락처

- 기술 지원: support@example.com
- 긴급 연락: +82-10-XXXX-XXXX
