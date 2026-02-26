# 🧠 문맥 인지형 설계자 (Context-Aware Designer) 아키텍처 기획서

현재 DAOM의 Designer-Engineer 구조는 매우 훌륭하지만, 한 가지 맹점이 있습니다. 
현재 **'설계자(Designer)'는 문서의 원본 내용을 전혀 보지 않고 오직 '사용자의 스키마(Model Configuration)'만 보고 작업 지시서를 만듭니다.**
따라서 시시각각 변하는 개별 문서들의 특수한 표 배치나 셀 병합 상태를 사전에 인지하여 맞춤형 지시를 내리지 못합니다.

이를 해결하기 위해, 설계자에게 **"문서 사전 검토(Document Pre-flight)" 권한**을 부여하는 새로운 아키텍처를 제안합니다.

---

## 1. 아키텍처 핵심 변경 사항: "문서를 읽고 지시서를 쓰는 설계자"

기존에는 `Schema -> Work Order` 생성 후 캐싱하여 모든 문서에 동일하게 적용했습니다.
새로운 아키텍처에서는 이를 **Two-Tier Designer 체제**로 변경합니다.

### 1-1. 정적(Static) 작업 지시서 생성 (기존과 동일, 캐싱됨)
- 스키마의 공통 규칙 및 필드 타입을 분석합니다.
- 비용 최적화를 위해 이 부분은 기존처럼 캐싱합니다.

### 1-2. 동적(Dynamic) 문맥 지시서 주입 (New!)
- OCR이 끝난 마크다운 텍스트(`Tagged Text`)가 나오면, **고속/경량 LLM(GPT-4o-mini)** 패턴 인식 전담반이 문서를 1초 만에 훑어봅니다.
- **주요 역할:**
  1.  **테이블 지도 매핑:** "표 1은 A, B, C 헤더를 지녔고, 표 2는 D, E 헤더를 가졌다."
  2.  **관계 파악:** "문단 3에 표 1과 표 2를 조인하기 위한 특정 조건(예: 할인율 10%)이 명시되어 있다."
  3.  **병합 탐지:** "표 2의 컬럼 A는 셀 병합되어 있어 아래 행들에 빈칸이 다수 존재한다."
- 이 분석 결과를 바탕으로 **문서 전용 특화 지시사항(Dynamic Context Rules)**을 정적 작업 지시서 하단에 결합(Merge)합니다.

---

## 2. 파이프라인 시퀀스 다이어그램 (As-Is vs To-Be)

### [As-Is] 눈 감고 지시하는 설계자
```text
[Schema] 👉 (Designer) 👉 [고정된 작업 지시서] 
                                    ⬇️
[OCR Text] 👉 (Engineer: 지시서 받고 알아서 문서 속에서 표 찾고 조인하며 낑낑댐) 👉 추출 지연 🐢
```

### [To-Be] 문서를 먼저 읽고 브리핑하는 설계자
```text
[Schema] 👉 (Designer: 정적 뼈대 조립) 
                                      ↘️
[OCR Text] 👉 (Context-Aware LLM) 👉 [동적 상황 보고서] 👉 (Designer: 두 개를 합침)
                                                                 ⬇️
(Engineer: "표 A는 2페이지에 있고, 병합된 셀은 복사해서 채우라고 지시서에 적혀있네! 바로 돌격!") 👉 고속 추출 🚀
```

---

## 3. 새로운 프롬프트 설계 (Context-Aware Report)

문맥 인지 전담 LLM(Context-Aware LLM)에게 던져야 할 핵심 프롬프트 템플릿입니다.

```text
[SYSTEM]
당신은 문서 구조 매핑 전문가입니다. 데이터를 직접 추출하지 마십시오.
제공된 문서를 아주 빠르게 스캔하여 아래의 JSON 구조로 '구조 지도(Structure Map)'만 반환하십시오.

[OUTPUT FORMAT]
{
  "table_map": [
    {
      "table_id": 1,
      "location": "Page 1, Paragraph 3",
      "headers": ["Item", "Qty", "Price"],
      "has_merged_cells": true,
      "recommendation_for_engineer": "이 표는 Item 컬럼이 병합되어 있으므로, 
                                      비어있는 값은 직전 행의 Item 값으로 채워넣어야 함."
    }
  ],
  "cross_references": [
    {
      "description": "할인 조건 및 특약",
      "location": "Page 3, Paragraph 1",
      "recommendation_for_engineer": "표 1의 Price를 계산할 때 반드시 이 위치의 할인 조건을 조인할 것."
    }
  ]
}
```

---

## 4. 구현 시 필요한 시스템 리소스 및 변경점

이 아키텍처를 도입하기 위해 필요한 실무적인 변경 포인트입니다.

1.  **경량 LLM 라우팅:** `beta_pipeline.py` 내부에 OpenAI 라우터를 추가하여, `Context-Aware Payload(위의 JSON)`를 뱉어내는 전용 비동기 함수 `_run_context_analyzer()`를 신설해야 합니다. 모델은 빠르고 저렴한 `gpt-4o-mini`로 고정합니다.
2.  **지시서 결합기(Merger):** 기존의 완벽하게 캐싱된 `work_order_json`에, 위에서 얻어낸 `table_map`과 `cross_references` 노드를 최상단에 주입(Injection)하는 로직을 엔지니어 호출 직전(`_run_engineer` 앞단)에 추가합니다.
3.  **Engineer Prompt 업데이트:** 엔지니어의 프롬프트에 *"지시서(Work Order) 상단에 동봉된 문서 구조 지도(Structure Map)를 최우선으로 참고하여 위치를 찾으시오"* 라는 룰을 추가합니다.

---

## 5. 결론 및 기대 효용

이 구조로 개편되면, 엔지니어 LLM은 **마치 내비게이션(동적 지시서)을 켜고 목적지(표 위치 및 병합 조건)를 찾아가는 것과 같은 효과**를 얻습니다.
*   **속도 증가:** 엔지니어가 엉뚱한 표를 읽거나 거대한 텍스트 안에서 헤매는 시간이 사라져 어텐션(Attention) 연산이 최적화됩니다.
*   **정확도 극대화:** 흩어진 테이블의 조인 조건이나 셀 병합 같은 고난도 변수들을 '사전 탐지기(Context LLM)'가 미리 짚어주므로 휴먼 에러를 방지할 수 있습니다. 
*   **토큰 가성비:** 정밀 추출용 비싼 GPT-4o를 오래 굴리지 않고, 싼 모델(mini)이 사전 정찰을 하므로 종합적인 API 호출 비용과 딜레이가 균형을 이룹니다.
