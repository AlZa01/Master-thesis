#!/usr/bin/env python
# coding: utf-8

import os
import json
import requests
from typing import Dict, Any, List, Optional


class YandexGPTClient:
    def __init__(
        self, folder_id: str=None, api_key: str=None, 
        instruction_text: str=None
    ):
        self.folder_id = folder_id or SETTINGS.yandex_folder_id
        self.api_key = api_key or SETTINGS.yandex_api_key
        self.base_url = 'https://llm.api.cloud.yandex.net/foundationModels/v1/completion'
        self.instruction_text = instruction_text 
        
        if not self.folder_id or not self.api_key:
            raise ValueError('Yandex Cloud folder_id and api_key must be provided.')
        
        self.headers = {
            'x-folder-id': folder_id,
            'Content-type': 'application/json',
            'Authorization': f'Api-key {api_key}'
        }
        
        msg = 'YandexGPTClient initialized successfully'
        print(msg)
    
    def call_yandexgpt(
        self, prompt: str, model_name: str='yandexgpt',
        max_tokens: int=1000, temperature: float=.1
    ) -> Optional[str]:
        try:
            req = {
                'modelUri': f'gpt://{self.folder_id}/{model_name}/latest',
                'completionOptions': {
                    'stream': False,
                    'temperature': temperature,
                    'maxTokens':  max_tokens
                },
                'messages': [
                    {
                        'role': 'system',
                        'text': self.instruction_text
                    },
                    {
                        'role': 'user',
                        'text': prompt
                    }
                ]
            }
            response = requests.post(
                self.base_url,
                headers=self.headers, 
                json=req,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            alternatives = result.get('result', {}).get('alternatives', [])
            if alternatives and isinstance(alternatives, list) and alternatives[0].get('message'):
                text = alternatives[0].get('message', {}).get('text', '')
            else:
                msg = f'LLM response structure unexpected: {result}'
                print(msg)
                text = ''
            return text
        
        except requests.exceptions.Timeout:
            msg = 'YandexGPT API call timed out'
            print(msg)
            return None
        except Exception as e:
            msg = f'YandexGPT API call failed: `{e}`'
            print(msg)
            return None
