# 4. 프론트엔드 가이드

> React 기반 SPA 프론트엔드의 아키텍처, 라우팅, 상태관리, 주요 컴포넌트를 설명합니다.

---

## 📁 디렉토리 구조

```
frontend/src/
├── App.tsx              # 앱 진입점 (라우팅, Provider 구성)
├── main.tsx             # React DOM 렌더링
├── index.css            # 전역 CSS (Tailwind, CSS 변수)
├── i18n.ts              # i18next 초기화 설정
│
├── auth/                # 인증 관련 (MSAL 설정, AuthProvider)
│   ├── authConfig.ts    # MSAL 인스턴스 설정
│   ├── AuthProvider.tsx # 인증 Context Provider
│   └── useAuth.ts       # 인증 훅
│
├── components/          # 공유 컴포넌트 (23 파일 + 6 하위 디렉토리)
│   ├── Sidebar.tsx      # 17KB — 사이드바 내비게이션
│   ├── ModelStudio.tsx  # 41KB — 모델 편집기 (최대 파일)
│   ├── ModelGallery.tsx # 14KB — 모델 갤러리 (기본 랜딩)
│   ├── UserManagement.tsx # 45KB — 사용자 관리
│   ├── AuditLogViewer.tsx # 13KB — 감사 로그 뷰어
│   ├── AdminSettings.tsx  # 10KB — 관리자 설정
│   ├── ui/              # shadcn/ui 기반 UI 프리미티브 (23 파일)
│   ├── studio/          # Model Studio 하위 컴포넌트 (8 파일)
│   ├── settings/        # 설정 관련 (3 파일)
│   ├── preview/         # 미리보기 관련 (2 파일)
│   ├── template/        # 템플릿 관련 (3 파일)
│   └── admin/           # 관리자 관련 (1 파일)
│
├── features/            # 기능별 모듈
│   ├── extraction/      # 데이터 추출 (6 파일)
│   ├── verification/    # 추출 검증/리뷰 (20 파일, 핵심)
│   ├── comparison/      # 이미지 비교 (2 파일)
│   └── quick/           # 빠른 추출 (1 파일)
│
├── hooks/               # 커스텀 훅 (4 파일)
├── i18n/                # 번역 파일
│   ├── ko.json          # 한국어
│   └── en.json          # 영어
├── lib/                 # API 유틸리티 (4 파일)
├── types/               # TypeScript 타입 정의 (4 파일)
└── utils/               # 유틸리티 함수 (4 파일)
```

---

## 🗺️ 라우팅 구조

> `react-router-dom` v7 기반. 라우팅은 `App.tsx`에서 정의됩니다.

| 경로 | 컴포넌트 | 설명 |
|------|---------|------|
| `/` | `WelcomeScreen` | 기본 랜딩 페이지 |
| `/login` | `LoginPage` | MSAL 로그인 |
| `/models` | `ModelGallery` | 모델 갤러리 (기본 대시보드) |
| `/models/:id` | `ModelView` | 모델 상세 보기 |
| `/models/:id/studio` | `ModelStudio` | 모델 편집기 (필드, 규칙, 참조데이터) |
| `/models/:id/logs` | `ExtractionLogList` | 추출 로그 목록 |
| `/models/:id/logs/:logId` | `ExtractionReviewView` | 추출 결과 검증/리뷰 (핵심 UI) |
| `/models/:id/extract` | `ExtractionPage` | 새 추출 실행 |
| `/models/:id/compare` | `ComparisonView` | 이미지 비교 |
| `/users` | `UserManagement` | 사용자 관리 |
| `/audit` | `AuditLogViewer` | 감사 로그 |
| `/settings` | `AdminSettings` | 시스템 설정 |
| `/profile` | `ProfilePage` | 개인 프로필 |
| `*` | `NotFoundPage` | 404 |

### Dual-Key Deep Linking

추출 결과 리뷰 화면은 **URL 파라미터로 상태를 동기화**합니다:

```
/models/:modelId/logs/:logId?tab=fields&field=premium_rate&page=2
```

| 파라미터 | 역할 |
|---------|------|
| `tab` | 활성 탭 (fields, raw, beta) |
| `field` | 선택된 필드 키 |
| `page` | PDF 페이지 번호 |
| `fileId` | 멀티 문서 시 파일 식별자 |

---

## 🔄 상태관리

### 1. TanStack Query (서버 상태)

API 호출과 캐싱을 담당합니다:

```tsx
// 모델 목록 조회 예시
const { data, isLoading } = useQuery({
  queryKey: ['models'],
  queryFn: () => api.get('/models').then(r => r.data),
  staleTime: 5 * 60 * 1000,  // 5분 캐시
});

// 추출 결과 폴링 예시
const { data: job } = useQuery({
  queryKey: ['job', jobId],
  queryFn: () => api.get(`/extraction-jobs/${jobId}`),
  refetchInterval: (data) => 
    data?.status === 'completed' ? false : 2000,  // 완료 전까지 2초 간격 폴링
});
```

### 2. React Context (클라이언트 상태)

주요 Context Provider:

| Context | 파일 | 역할 |
|---------|------|------|
| `ExtractionContext` | `features/extraction/` | 추출 워크플로우 전역 상태 (결과, 하이라이트, 폴링) |
| `AuthProvider` | `auth/` | 인증 상태, 토큰, 사용자 정보 |
| `SiteConfigProvider` | `components/` | 사이트 설정, 메뉴 구성, 테마 |
| `ThemeProvider` | `components/` | 다크/라이트 테마 전환 |

### 3. URL 상태 동기화 (Route-to-State)

```tsx
// URL 파라미터 ↔ 컴포넌트 상태 동기화 패턴
const [searchParams, setSearchParams] = useSearchParams();
const activeTab = searchParams.get('tab') || 'fields';

const handleTabChange = (tab: string) => {
  setSearchParams(prev => {
    prev.set('tab', tab);
    return prev;
  });
};
```

---

## 🧩 핵심 컴포넌트

### Model Studio (`ModelStudio.tsx`, 41KB)

모델 편집의 핵심 UI. 다음 섹션을 포함:

```
┌──────────────────────────────────────┐
│ 모델 정보 (이름, 설명, 상태)          │
├──────────────────────────────────────┤
│ 필드 정의 (Sortable Drag & Drop)     │
│   ├── 기본 필드 (text, number, date)  │
│   └── 중첩 테이블 필드 (children)     │
├──────────────────────────────────────┤
│ 전역 규칙 (Global Rules)             │
├──────────────────────────────────────┤
│ 참조 데이터 (Reference Data)          │
├──────────────────────────────────────┤
│ Beta 기능 토글                       │
└──────────────────────────────────────┘
```

### Extraction Review View (`ExtractionReviewView.tsx`)

추출 결과 검증의 핵심 UI. Evidence Hub 패턴 사용:

```
┌─────────────────────┬──────────────────────┐
│     왼쪽 패널        │      오른쪽 패널      │
│                     │                      │
│  📄 PDF 미리보기     │  📊 추출 결과 필드     │
│  (하이라이팅 지원)    │  (편집 가능)          │
│                     │                      │
│  📝 OCR 텍스트      │  🔬 Beta 파싱 결과    │
│                     │                      │
│  📊 테이블 뷰       │  { } Raw JSON        │
│                     │                      │
│  (ResizablePanel)   │  (탭 전환)            │
└─────────────────────┴──────────────────────┘
```

### PDF 하이라이팅

추출된 값의 원본 위치를 PDF에서 하이라이팅합니다:

```tsx
// 하이라이트 데이터 구조
interface HighlightArea {
  pageIndex: number;     // 페이지 인덱스 (0-based)
  left: number;          // 좌표 (% 단위)
  top: number;
  width: number;
  height: number;
  color: string;         // 하이라이트 색상
  fieldKey: string;      // 연관된 필드 키
  fileId?: string;       // 멀티 문서 지원
}
```

---

## 🌐 다국어 (i18n)

### 구조

```
src/i18n/
├── ko.json    # 한국어 번역
├── en.json    # 영어 번역
└── (추가 언어 확장 가능)
```

### 사용법

```tsx
import { useTranslation } from 'react-i18next';

function MyComponent() {
  const { t } = useTranslation();
  return <h1>{t('models.title')}</h1>;
}
```

### 번역 파일 구조 예시

```json
{
  "common": {
    "save": "저장",
    "cancel": "취소",
    "delete": "삭제"
  },
  "models": {
    "title": "모델 관리",
    "create": "모델 생성",
    "fields": "필드 정의"
  },
  "extraction": {
    "start": "추출 시작",
    "status": {
      "pending": "대기 중",
      "processing": "처리 중",
      "completed": "완료",
      "failed": "실패"
    }
  }
}
```

---

## 🎨 UI 컴포넌트 시스템

### shadcn/ui 베이스

`components/ui/` 디렉토리에 Radix UI 기반 프리미티브를 사용합니다:

| 컴포넌트 | Radix 베이스 | 용도 |
|---------|-------------|------|
| Dialog | `@radix-ui/react-dialog` | 모달 |
| DropdownMenu | `@radix-ui/react-dropdown-menu` | 드롭다운 메뉴 |
| Tabs | `@radix-ui/react-tabs` | 탭 전환 |
| Switch | `@radix-ui/react-switch` | 토글 스위치 |
| Tooltip | `@radix-ui/react-tooltip` | 툴팁 |
| Checkbox | `@radix-ui/react-checkbox` | 체크박스 |
| ScrollArea | `@radix-ui/react-scroll-area` | 스크롤 영역 |
| Slider | `@radix-ui/react-slider` | 슬라이더 |
| Popover | `@radix-ui/react-popover` | 팝오버 |

### CSS 변수 패턴

```css
/* index.css — 테마 변수 */
:root {
  --background: 0 0% 100%;
  --foreground: 222.2 84% 4.9%;
  --primary: 221.2 83.2% 53.3%;
  --primary-foreground: 210 40% 98%;
  --destructive: 0 84.2% 60.2%;
  /* ... */
}

.dark {
  --background: 222.2 84% 4.9%;
  --foreground: 210 40% 98%;
}
```

---

## ⚡ API 클라이언트

`src/lib/` 에 위치한 Axios 기반 API 클라이언트:

```tsx
// lib/api.ts
import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
});

// 자동 토큰 주입
api.interceptors.request.use(async (config) => {
  const token = await getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;
```

---

## 📝 새 페이지 추가 방법

### 1. 컴포넌트 생성

```tsx
// src/components/MyNewPage.tsx
import { useTranslation } from 'react-i18next';

export default function MyNewPage() {
  const { t } = useTranslation();
  
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold">{t('myPage.title')}</h1>
      {/* 컨텐츠 */}
    </div>
  );
}
```

### 2. 라우트 등록 (`App.tsx`)

```tsx
<Route path="/my-page" element={<MyNewPage />} />
```

### 3. 사이드바 메뉴 등록 (`Sidebar.tsx`)

```tsx
// Sidebar.tsx — 메뉴 항목 추가
{ path: '/my-page', icon: <FileIcon />, label: t('sidebar.myPage') }
```

### 4. 번역 추가 (`i18n/ko.json`)

```json
{
  "sidebar": { "myPage": "새 페이지" },
  "myPage": { "title": "새 페이지 제목" }
}
```

---

## ⚠️ 빌드 주의사항

### TypeScript Strict 모드

프로젝트는 엄격한 TypeScript 설정을 사용합니다:

```
- ❌ 사용하지 않는 import → build 실패
- ❌ 사용하지 않는 변수 → build 실패
- ❌ verbatimModuleSyntax 위반 → build 실패
- ❌ any 타입 남용 → lint 경고
```

### 빌드 전 체크리스트

```bash
# 1. 타입 체크
npx tsc --noEmit

# 2. 린트
npm run lint

# 3. 전체 빌드
npm run build
```

---

**다음**: [05. 추출 파이프라인](05-extraction-pipeline.md)에서 핵심 기능인 문서 추출의 전체 흐름을 파악합니다.
