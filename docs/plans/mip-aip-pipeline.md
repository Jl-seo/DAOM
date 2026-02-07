# MIP/AIP 보호 해제 + Private Blob 파이프라인 (계획)

> **Status**: 📋 계획만 정리 — 구현 보류
> **Priority**: P2 (인프라/권한 선행 필요)

## 목표

사용자가 MIP/AIP 보호된 파일을 업로드하면 자동으로 보호를 해제하고,
Private Endpoint를 통해 Blob에 저장한 뒤 SAS URL로 뷰어에서 사용.

## 파이프라인

```
업로드 → MIP 감지 → 복호화 → Blob(Private EP) → SAS URL → 추출 파이프라인
```

## 구현 방법

| 방법 | 핵심 | 장단점 |
|------|------|--------|
| **MIP SDK (Python)** | `mip` 패키지 직접 사용 | 완전 제어 / Docker 빌드 복잡 |
| **Graph API** | MS Graph driveItem API | 관리형, 간단 / latency, 라이선스 |

**추천**: 하이브리드 — 감지는 로컬(`python-magic`), 복호화는 Graph API fallback

## 선행 조건

1. **Azure AD 앱 등록** — `Azure Rights Management Services` API 권한
2. **RMS SuperUser** — 서비스 주체가 모든 보호 문서 복호화 가능
3. **Blob Private Endpoint** — VNet 내 Private Link, 외부 차단
4. **MIP SDK Docker 호환성** — 네이티브 바이너리, ARM64 지원 확인

## 변경 대상 파일 (예상)

| 파일 | 변경 내용 |
|------|----------|
| `backend/app/services/mip_service.py` | [NEW] MIP 감지/복호화 서비스 |
| `backend/app/services/blob_service.py` | Private EP 업로드 + SAS 생성 |
| `backend/app/api/extraction.py` | 업로드 시 MIP 파이프라인 호출 |
| `infra/modules/storage.bicep` | Private Endpoint 구성 |
| `infra/modules/identity.bicep` | RMS 권한 할당 |

## 참고

- 현재 DAOM은 이미 `azure-storage-blob` + SAS URL 패턴 사용 중
- Private Endpoint는 Bicep IaC로 추가 가능
- 코드 구현 자체보다 인프라/권한 세팅이 병목
