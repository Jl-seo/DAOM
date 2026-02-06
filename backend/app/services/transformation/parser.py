import json
import logging
import asyncio
from typing import List, Dict, Any
from app.core.config import settings
from openai import AsyncAzureOpenAI
from app.services.transformation.engine import TransformationRule

logger = logging.getLogger(__name__)

class RuleParser:
    def __init__(self):
        self.client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )
        self.deployment_name = settings.AZURE_OPENAI_DEPLOYMENT_NAME

    async def parse_natural_language(self, text: str, available_fields: List[str]) -> List[TransformationRule]:
        """
        Convert natural language text into transformation rules using LLM.
        """
        system_prompt = f"""
        You are a Transformation Rule Generator. 
        Your goal is to convert natural language instructions into a structured JSON configuration for a data transformation engine.
        
        ### Capabilities
        The engine supports these rule types:
        
        1. **EXPLODE**: Create combinations from lists.
           - Config: {{ "sources": [{{"field": "SourceList", "as": "Alias"}}], "output_field": "OutputList" }}
           
        2. **CALCULATE**: Apply math or logic.
           - Config: {{ 
               "target_list": "OutputList", 
               "calculations": [
                 {{ "condition": "POL == 'Incheon'", "field": "Rate", "expression": "Base_Rate + 50" }}
               ]
             }}
             
        3. **VALIDATE**: Check conditions.
        
        ### Available Fields (Variables)
        You can referece these variables: {json.dumps(available_fields)}
        User might use @{{FieldName}} or just FieldName syntax. Treat them as valid variables.
        
        ### Output Format
        Return ONLY a JSON array of rule objects. No markdown, no explanations.
        Example:
        [
          {{
            "type": "EXPLODE",
            "config": {{ ... }}
          }}
        ]
        """
        
        try:
            # 타임아웃 10초 설정 (MVP 빠른 응답 위해)
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.deployment_name,
                    messages=[
                        {"role": "system", "content": system_prompt + "\n\nJSON output only."},
                        {"role": "user", "content": text}
                    ],
                    temperature=0,
                    response_format={"type": "json_object"}
                ),
                timeout=10.0
            )
            
            content = response.choices[0].message.content
            parsed_data = json.loads(content)
            
            # Handle various JSON output formats from LLM
            if isinstance(parsed_data, dict):
                rules_list = parsed_data.get("rules", []) or parsed_data.get("items", [])
                # Fallback if direct list is inside a key
                if not rules_list and len(parsed_data) == 1:
                    rules_list = list(parsed_data.values())[0]
            elif isinstance(parsed_data, list):
                rules_list = parsed_data
            else:
                rules_list = []
                
            return [TransformationRule(**r) for r in rules_list]
            
        except asyncio.TimeoutError:
            logger.error("LLM request timed out while generating rules.")
            return []
            
        except Exception as e:
            logger.error(f"Error parsing rules: {e}")
            return []
