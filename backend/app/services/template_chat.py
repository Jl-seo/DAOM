"""
Template chat service - Uses LLM to convert natural language to template configuration
"""
from openai import AzureOpenAI
from app.core.config import settings
import json
import logging

logger = logging.getLogger(__name__)

TEMPLATE_SYSTEM_PROMPT = """당신은 데이터 출력 템플릿 디자이너입니다.
사용자의 요청을 듣고 TemplateConfig JSON을 생성/수정합니다.

## 사용 가능한 필드:
{model_fields}

## TemplateConfig 스키마:
{{
  "layout": "table" | "card" | "report" | "summary",
  "header": {{
    "logo": boolean,
    "title": string,
    "subtitle": string
  }},
  "footer": {{
    "showDate": boolean,
    "pageNumbers": boolean,
    "customText": string
  }},
  "columns": [
    {{
      "field": "필드키",
      "label": "표시 라벨",
      "align": "left" | "center" | "right",
      "format": "text" | "currency" | "date" | "percent" | "number",
      "style": {{ "color": "#색상코드", "bold": boolean }}
    }}
  ],
  "aggregation": {{
    "showTotal": boolean,
    "showAverage": boolean,
    "showCount": boolean,
    "groupBy": "필드키"
  }},
  "style": {{
    "theme": "modern" | "classic" | "minimal",
    "primaryColor": "#색상코드",
    "fontSize": 숫자
  }}
}}

## 규칙:
1. 사용자 요청에 맞게 현재 config를 수정
2. 변경된 부분만 응답 (전체가 아닌 delta)
3. 친근하게 응답하고 확인 질문
4. JSON은 반드시 유효해야 함

## 응답 형식 (반드시 이 JSON 형식으로):
{{
  "message": "사용자에게 보여줄 친근한 메시지",
  "config": {{ ... 업데이트된 설정 ... }}
}}
"""


def get_template_client():
    """Get OpenAI client for template chat"""
    if not settings.AZURE_OPENAI_ENDPOINT or not settings.AZURE_OPENAI_API_KEY:
        return None
    
    return AzureOpenAI(
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_key=settings.AZURE_OPENAI_API_KEY,
        api_version="2024-02-15-preview"
    )


async def process_template_chat(
    message: str,
    current_config: dict,
    model_fields: list[dict]
) -> dict:
    """
    Process user message and generate template config update
    
    Args:
        message: User's natural language request
        current_config: Current template configuration
        model_fields: Available fields from the model
    
    Returns:
        dict with 'message' and 'config' keys
    """
    client = get_template_client()
    
    if not client:
        logger.warning("OpenAI client not configured, using fallback")
        return fallback_process(message, current_config, model_fields)
    
    try:
        # Format model fields for prompt
        fields_str = json.dumps(model_fields, ensure_ascii=False, indent=2)
        
        system_prompt = TEMPLATE_SYSTEM_PROMPT.format(model_fields=fields_str)
        
        user_prompt = f"""현재 템플릿 설정:
{json.dumps(current_config, ensure_ascii=False, indent=2)}

사용자 요청: {message}

위 요청에 맞게 템플릿을 수정해주세요."""

        response = client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT or "gpt-4.1",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=1000,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content
        result = json.loads(result_text)
        
        return {
            "message": result.get("message", "템플릿을 업데이트했어요!"),
            "config": result.get("config", {})
        }
        
    except Exception as e:
        logger.error(f"Template chat error: {e}")
        return fallback_process(message, current_config, model_fields)


def fallback_process(message: str, current_config: dict, model_fields: list[dict]) -> dict:
    """Fallback processing when LLM is not available"""
    lower_msg = message.lower()
    config = dict(current_config)
    response_msg = ""
    
    if '테이블' in lower_msg or '표' in lower_msg:
        config['layout'] = 'table'
        config['columns'] = [
            {
                'field': f.get('key', ''),
                'label': f.get('label', f.get('key', '')),
                'align': 'right' if f.get('type') == 'number' else 'left',
                'format': 'number' if f.get('type') == 'number' else 'text'
            }
            for f in model_fields
        ]
        response_msg = f"테이블 형태로 변경했어요! {len(model_fields)}개 컬럼을 포함했습니다."
    
    elif '헤더' in lower_msg or '제목' in lower_msg:
        import re
        title_match = re.search(r'[\'\"\""](.+?)[\'\"\""]', message)
        config['header'] = {
            **config.get('header', {}),
            'title': title_match.group(1) if title_match else '데이터 보고서'
        }
        response_msg = "헤더에 제목을 추가했어요!"
    
    elif '합계' in lower_msg or '총' in lower_msg:
        config['aggregation'] = {
            **config.get('aggregation', {}),
            'showTotal': True
        }
        response_msg = "합계 행을 추가했어요!"
    
    elif '색' in lower_msg or '컬러' in lower_msg:
        if '빨간' in lower_msg or 'red' in lower_msg:
            config['style'] = {**config.get('style', {}), 'primaryColor': '#ef4444'}
            response_msg = "주요 색상을 빨간색으로 변경했어요!"
        elif '파란' in lower_msg or 'blue' in lower_msg:
            config['style'] = {**config.get('style', {}), 'primaryColor': '#3b82f6'}
            response_msg = "주요 색상을 파란색으로 변경했어요!"
        else:
            response_msg = "어떤 색상을 원하시나요? 예: '빨간색으로 해줘'"
    
    elif '크게' in lower_msg or '폰트' in lower_msg:
        current_size = config.get('style', {}).get('fontSize', 14)
        config['style'] = {**config.get('style', {}), 'fontSize': current_size + 2}
        response_msg = f"폰트 크기를 {current_size + 2}pt로 키웠어요!"
    
    else:
        response_msg = "죄송해요, 잘 이해하지 못했어요. '테이블로 만들어줘', '헤더 추가해줘' 같이 말씀해주세요!"
    
    return {
        "message": response_msg,
        "config": config
    }
