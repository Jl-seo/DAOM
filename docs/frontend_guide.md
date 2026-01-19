# DAOM 프론트엔드 아키텍처 가이드

> React + TypeScript + Vite 기반 프론트엔드 시스템의 구조와 핵심 컴포넌트를 설명합니다.

---

## 📁 디렉토리 구조

```
frontend/src/
├── App.tsx                 # 메인 앱, 라우팅
├── main.tsx               # 진입점, Provider 설정
├── index.css              # 전역 스타일, CSS 변수
│
├── auth/                  # 인증 (Entra ID)
│   ├── AuthProvider.tsx   # 인증 Context
│   ├── msalConfig.ts      # MSAL 설정
│   └── index.ts
│
├── components/            # 공용 컴포넌트
│   ├── ui/               # shadcn/ui 기반 UI 요소
│   ├── settings/         # 설정 관련 컴포넌트
│   ├── studio/           # 모델 스튜디오 컴포넌트
│   ├── Sidebar.tsx       # 사이드바 네비게이션
│   ├── AdminSettings.tsx # 관리자 설정 페이지
│   └── ModelStudio.tsx   # 모델 스튜디오 메인
│
├── features/             # 기능별 모듈
│   ├── extraction/       # 문서 추출 기능
│   ├── verification/     # 추출 결과 검증
│   └── comparison/       # 문서 비교 기능
│
├── hooks/                # 커스텀 훅
├── i18n/                 # 다국어 지원
├── types/                # TypeScript 타입 정의
└── utils/                # 유틸리티 함수
```

---

## 🎨 핵심 컴포넌트

### App.tsx
**역할**: 메인 라우팅 및 레이아웃

```tsx
// 주요 뷰
- 'welcome'     → WelcomeScreen (대시보드)
- 'extraction'  → QuickExtractionView (빠른 추출)
- 'model-*'     → ModelView (모델별 추출)
- 'settings-*'  → AdminSettings (관리자 설정)
```

### Sidebar.tsx
**역할**: 좌측 네비게이션 메뉴

주요 기능:
- 동적 모델 목록 표시
- 권한 기반 메뉴 필터링
- 테마 토글
- 언어 선택

### ModelStudio.tsx
**역할**: 추출 모델 정의 UI

주요 기능:
- 필드 추가/편집/삭제
- 글로벌 규칙 설정
- 샘플 문서 업로드
- AI 자동 필드 생성

---

## 📂 features 상세

### extraction/ - 문서 추출
```
extraction/
├── components/
│   ├── ExtractionGrid.tsx      # 추출 결과 그리드
│   ├── AllExtractionHistory.tsx # 전체 추출 기록
│   └── BatchUpload.tsx         # 배치 업로드
└── hooks/
    └── useExtraction.ts        # 추출 상태 관리
```

### verification/ - 결과 검증
```
verification/
├── components/
│   ├── PDFViewer.tsx           # PDF 뷰어
│   ├── ExtractionPreview.tsx   # 추출 미리보기
│   ├── ExtractionReviewView.tsx # 결과 검토 UI
│   └── ExtractionUploadView.tsx # 업로드 + 추출
├── context/
│   └── ExtractionContext.tsx   # 추출 상태 Context
└── types.ts                    # 타입 정의
```

---

## 🔧 주요 훅 (Hooks)

### useAuth() - 인증
```tsx
const { user, isAuthenticated, login, logout } = useAuth()
```

### useSiteConfig() - 사이트 설정
```tsx
const { config, updateConfig, resolvedTheme } = useSiteConfig()
```

### useTranslation() - 다국어
```tsx
const { t, i18n } = useTranslation()
// t('common.actions.save') → "저장"
```

---

## 🌐 다국어 (i18n)

### 지원 언어
- `ko`: 한국어 (기본)
- `en`: English

### 사용법
```tsx
import { useTranslation } from 'react-i18next'

function MyComponent() {
    const { t } = useTranslation()
    return <button>{t('common.actions.save')}</button>
}
```

### 번역 파일 위치
```
src/i18n/locales/
├── ko.json   # 한국어
└── en.json   # 영어
```

### 번역 키 구조
```json
{
  "common": {
    "actions": { "save": "저장", "cancel": "취소" },
    "labels": { "user": "사용자", "settings": "설정" }
  },
  "extraction": {
    "upload": { "drag_drop": "파일을 드래그하세요" }
  },
  "menu": {
    "upload": "문서 업로드",
    "history": "추출 히스토리"
  }
}
```

---

## 🎨 스타일 시스템

### CSS 변수 (index.css)
```css
:root {
  --background: 0 0% 100%;
  --foreground: 240 10% 3.9%;
  --primary: 221 83% 53%;
  --primary-foreground: 210 20% 98%;
  /* ... */
}

.dark {
  --background: 240 10% 3.9%;
  --foreground: 0 0% 98%;
  /* ... */
}
```

### Tailwind 사용
```tsx
<div className="bg-background text-foreground p-4 rounded-lg">
  <button className="bg-primary text-primary-foreground px-4 py-2">
    클릭
  </button>
</div>
```

---

## 📡 API 통신

### 기본 설정
```tsx
// src/constants/index.ts
export const API_CONFIG = {
  BASE_URL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'
}
```

### 사용 예시
```tsx
import axios from 'axios'
import { API_CONFIG } from '../constants'

const response = await axios.get(`${API_CONFIG.BASE_URL}/models`)
```

---

## 🔒 인증 흐름

### 1. 로그인
```tsx
// auth/AuthProvider.tsx
const { login } = useAuth()
await login()  // Entra ID 팝업
```

### 2. 토큰 사용
```tsx
// API 호출 시 자동으로 토큰 첨부
axios.defaults.headers.common['Authorization'] = `Bearer ${token}`
```

### 3. 보호된 라우트
```tsx
function App() {
  const { isAuthenticated } = useAuth()
  
  if (!isAuthenticated) {
    return <LoginPage />
  }
  
  return <MainApp />
}
```

---

## 🚀 로컬 실행

```bash
cd frontend
npm install

# 환경변수 설정
echo "VITE_API_URL=http://localhost:8000/api/v1" > .env.local

# 개발 서버 실행
npm run dev
```

접속: http://localhost:5173

---

## 📦 빌드 & 배포

```bash
# 프로덕션 빌드
npm run build

# 빌드 결과: dist/ 폴더
# nginx 또는 Container Apps로 서빙
```

---

## 🧪 테스트

```bash
# 단위 테스트
npm run test

# 타입 체크
npm run typecheck

# 린트
npm run lint
```
