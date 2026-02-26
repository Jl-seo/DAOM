# DAOM 이미지 비교 분석 기능 코드 리뷰 결과 보고서

**작성일**: 2026-02-23
**대상 파일**: 
- `backend/app/services/comparison_service.py`
- `backend/app/services/pixel_diff.py`

본 문서는 DAOM 시스템에 정의된 "3계층 컴포넌트 아키텍처 기반의 이미지 비교 분석 기능" 명세서가 실제 백엔드 코드(`comparison_service.py`, `pixel_diff.py`)에 명확하게 구현 및 적용되어 있는지 검토한 결과입니다.

---

## 1. 3계층 컴포넌트 아키텍처 적용 여부: ✅ 정상 구현됨

코드상에서 물리적 검증(SSIM), 시각 의미 검증(Vision), 의미적/논리적 검증(LLM)이 3개 계층으로 명확히 구분되어 병렬 및 순차 파이프라인으로 구성되어 있습니다.

- **Layer 1 (Physical)**: `pixel_diff.calculate_ssim`이 호출되어 SSIM 점수와 차이점(diffs) 객체를 추출합니다.
- **Layer 2 (Visual)**: `VisionService.analyze_image`가 옵션(`use_vision=True`)에 따라 비동기 병렬(`asyncio.gather`)로 호출되어 메타데이터를 가져옵니다.
- **Layer 3 (Semantic)**: `client.chat.completions.create` (GPT-4o 등)이 호출되며, 1/2계층의 분석 결과가 컨텍스트(`ssim_context`, `vision_context`)로 주입됩니다.

## 2. 할루시네이션(환각) 완벽 차단 관문(Fast-Path Gate): ✅ 정상 구현됨

시간/비용 낭비와 환각 현상 방지를 위한 "Early Return (조기 종료)" 로직이 코드에 2중으로 정확히 적용되어 있습니다.

1. **글로벌 SSIM 점수 게이트**: `ssim_global_score >= ssim_identity_threshold(기본 95%)` 조건이 충족되면 LLM 호출을 건너뛰고 빈 배열을 반환하는 코드가 구현되어 있습니다. (`skipped_llm: True`)
2. **SSIM Diffs 0건 게이트**: 원본과 대조군의 차이 영역이 하나도 검출되지 않으면(`not ssim_diffs`), LLM 호출 없이 즉각 빈 배열을 반환(`skipped_llm: True`)하는 방어 로직이 적용되어 있습니다. (`skip_llm_if_identical` 옵션 지원)

## 3. 크롭 레벨(Crop-Level) 비교: ✅ 정상 구현됨

LLM이 국소적인 변화를 놓치는 현상을 방지하기 위한 크롭 데이터 주입(Crop-Level Verification) 설계가 프롬프트 메시지 조립부(`user_message.append`)에 정확히 구현되어 있습니다.

- `ssim_diffs[:5]`를 통해 검출된 **가장 큰 변화 영역 최대 5곳**의 bounding box 정보를 바탕으로 원본 이미지와 후보 이미지의 특정 부분을 잘라내어(crop) Base64로 인코딩한 이미지를 각각 LLM에게 전달하고 있습니다. (`Diff #{i} - Baseline Image Crop:`, `Candidate Image Crop:`)

## 4. 예외/무시 규칙(Ignore Rules) 통제: ✅ 정상/고도화 구현됨

명세서에서 소개한 사용자 설정 무시 규칙 및 강제 방어 코드(Anti-Hallucination)가 LLM의 `system_prompt`와 배열 필터링에 다중 구조로 잘 적용되어 있습니다.

- **위치 (`ignore_position`) / 색상 (`ignore_color`) / 폰트 (`ignore_font`) / 압축 노이즈 (`ignore_compression_noise`)**: 해당 옵션이 True일 때 프롬프트 텍스트(`ignore_rules_list`)에 각각의 무시 지시어가 추가됩니다.
- **강제 로고/레이아웃 조건**: 로고나 워터마크의 미세한 변화는 무시하고 요소 전체 누락 등 명백한 경우에만 오류로 잡으라는 하드코딩된 시스템 지시어가 `anti_hallucination_instruction`과 함께 주입되고 있습니다.
- **포스트 필터링(Post-processing)**: 
  - LLM이 내뱉는 `confidence` 점수가 `conf_threshold`(기본 0.85) 이하인 항목들을 프로그램 로직 단에서 제거하는 필터링(Post-process 1)이 적용되어 있습니다.
  - LLM이 지시어를 어기고 프론트가 지정하지 않은 카테고리의 차이점을 보고할 경우, Python 단에서 `allowed_categories` / `excluded_categories`를 검사하여 억지로 삭제(Post-process 2)하는 "Depth in Defense(다층 방어)" 설계가 적용되었습니다. 

## 5. 이미지 자동 정렬(Alignment): ✅ 정상 구현됨

문서 스캔 각도 차이 극복을 위해 `pixel_diff.py` 쪽에 `align_images` 함수가 구현되어 있습니다.
- OpenCV의 `ORB` 특징점 매칭 알고리즘과 `cv2.findHomography`, `cv2.warpPerspective`를 사용해 대상 이미지를 원본 이미지와 기하학적으로 일치시키는 정렬부 코드가 존재하며, 매칭에 실패하더라도 원본 크기에 맞추는 Fallback(단순 리사이징) 처리가 견고하게 들어있습니다.

---

# 🕵️‍♂️ 종합 평가 및 제언 (Review Summary)

기능 설명서에 기재된 모든 아키텍처 요구사항이 **놀라울 정도로 완벽하고 꼼꼼하게 `comparison_service.py`와 `pixel_diff.py`에 적용**되어 있습니다. 
특히 빠른 조기 종료(Fast-path)를 통한 비용 절감 도모, Python 단계에서의 2단계 Post-filter 적용 설계가 엔터프라이즈 환경에서의 안정성 및 방어적 프로그래밍(Defensive Programming) 관점에서 매우 훌륭합니다.

**소소한 개선/권장 사항 (Minor Suggestions for the Future):**

1. `pixel_diff.py` 내부 `calculate_ssim` 함수 내 `dynamic_min_area = max(min_area, (w1 * h1) // 50000)` 처리는 고해상도 초미세 노이즈를 거르기에 좋은 아이디어입니다. 추후 해상도가 극단적으로 작거나 큰 이미지가 들어올 것에 대비해, Threshold의 상한선(Max Cap) 정도만 한 번 더 안전제로 잡아 두는 것을 추천합니다.
2. `VisionService.analyze_image`가 활성화될 경우, Vision API 타임아웃 오류 시 비교 파이프라인 전체가 죽는 것을 방지하기 위해 fallback 로직을 한 겹 더 강화하는 것도 좋습니다. (현재는 `return_exceptions=True`로 gather에서 분기 처리는 되어 있어 프로그램이 뻗지는 않습니다.)

---
*별도의 코드 수정 사항 없이 현재 구현된 코드를 그대로 운영하여도 요구사항을 완벽히 만족합니다.*
