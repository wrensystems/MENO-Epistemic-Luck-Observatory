"""Bounded, text-only OpenAI Responses adapter; no SDK or automatic retries."""
import base64
import http.client
import json
import math
import os
import re
import urllib.error
import urllib.request

from .providers import NoRedirect, ProviderError, valid_tokens


DEFAULT_OPENAI_MODEL = 'gpt-6.1-sol'
# Reviewed standard/global rates, <=272K input tokens, no cache breakpoints.
OPENAI_PROFILES = {
    'gpt-6-astra': {'reasoning_effort': 'max', 'temperature': None,
                    'input_usd_per_million': 10, 'output_usd_per_million': 50},
    'gpt-6.1-sol': {'reasoning_effort': 'medium', 'temperature': None,
                    'input_usd_per_million': 2, 'output_usd_per_million': 10},
    'gpt-6-luna': {'reasoning_effort': 'none', 'temperature': 0,
                   'input_usd_per_million': .1, 'output_usd_per_million': .5},
}


def openai_defaults():
    """Fields for a new study; no budget, protocol approval or live activation."""
    return {'provider': 'openai', 'model': DEFAULT_OPENAI_MODEL,
            'api_version': 'responses-v1', 'evidence_kind': 'model_generated',
            **OPENAI_PROFILES[DEFAULT_OPENAI_MODEL]}


def transport(method, path, payload, key, timeout):
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
    for variable, header in [('OPENAI_PROJECT_ID', 'OpenAI-Project'), ('OPENAI_ORG_ID', 'OpenAI-Organization')]:
        if os.environ.get(variable):
            headers[header] = os.environ[variable]
    # urllib's header errors can echo the full value, including credentials.
    if any(any(ord(char) < 32 or ord(char) > 126 for char in value) for value in headers.values()):
        raise ProviderError('invalid_auth_header')
    request = urllib.request.Request('https://api.openai.com/v1/' + path,
        data=None if payload is None else json.dumps(payload, allow_nan=False).encode('utf-8'),
        headers=headers, method=method)
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
            request_id = response.headers.get('x-request-id')
            try:
                body = response.read()
            except http.client.IncompleteRead as exc:
                raise ProviderError('response_uncertain', raw={
                    'body_base64': base64.b64encode(exc.partial).decode('ascii'),
                    '_request_id': request_id}) from None
            try:
                raw = json.loads(body)
            except (ValueError, UnicodeError):
                raise ProviderError('response_uncertain', raw={'body_base64': base64.b64encode(body).decode('ascii'),
                                                             '_request_id': request_id}) from None
            if not isinstance(raw, dict):
                raise ProviderError('response_uncertain', raw={'body': raw, '_request_id': request_id})
            raw['_request_id'] = request_id
            return raw
    except urllib.error.HTTPError as exc:
        try:
            delay = float(exc.headers.get('retry-after', 0))
            if not math.isfinite(delay) or delay < 0:
                delay = 0
        except (ValueError, TypeError):
            delay = 0
        raise ProviderError(f'http_{exc.code}', retryable=exc.code in (408, 409, 429, 500, 502, 503, 504),
                            retry_after=delay) from None
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
        raise ProviderError('transport_uncertain') from None
    except (ValueError, TypeError):
        raise ProviderError('response_uncertain') from None


class OpenAIProvider:
    name = 'openai'

    def __init__(self, transport=None):
        self._key = os.environ.get('OPENAI_API_KEY')
        if not self._key:
            raise ValueError('Set OPENAI_API_KEY securely in the process environment')
        self._transport = transport or globals()['transport']

    def _call(self, method, path, payload, timeout):
        return self._transport(method, path, payload, self._key, timeout)

    def check_model(self, model):
        if not re.fullmatch(r'[A-Za-z0-9._-]+', model):
            raise ValueError('Invalid model identifier')
        raw = self._call('GET', 'models/' + model, None, 30)
        if raw.get('object') != 'model' or not isinstance(raw.get('id'), str):
            raise ProviderError('invalid_model_metadata')
        return {'id': raw['id'], 'object': raw['object']}

    def count_tokens(self, request):
        raw = self._call('POST', 'responses/input_tokens',
                         {'model': request['model'], 'input': request['prompt'],
                          'reasoning': {'effort': request.get('reasoning_effort', 'none')}}, request['timeout_seconds'])
        return valid_tokens(raw.get('input_tokens'))

    def generate(self, request):
        # Explicit mode with no breakpoints avoids cache writes/read pricing.
        payload = {'model': request['model'], 'input': request['prompt'],
                   'max_output_tokens': request['max_output_tokens'],
                   'reasoning': {'effort': request.get('reasoning_effort', 'none')}, 'store': False, 'tools': [],
                   'service_tier': 'default', 'prompt_cache_options': {'mode': 'explicit'}}
        if payload['reasoning']['effort'] == 'none':
            payload['temperature'] = request['temperature']
        raw = self._call('POST', 'responses', payload, request['timeout_seconds'])
        try:
            valid_tokens(raw['usage']['input_tokens'])
            valid_tokens(raw['usage']['output_tokens'])
            if raw['status'] != 'completed':
                raise ProviderError('incomplete_generation', raw=raw)
            if not isinstance(raw['model'], str) or not raw['model']:
                raise ValueError('Missing resolved model')
            output = raw['output']
            if not isinstance(output, list) or not output:
                raise ValueError('Missing output')
            texts = []
            for item in output:
                if isinstance(item, dict) and item.get('type') == 'reasoning':
                    if (not isinstance(item.get('id'), str) or not item['id']
                            or item.get('status', 'completed') != 'completed'
                            or not isinstance(item.get('summary'), list)
                            or any(not isinstance(s, dict) or s.get('type') != 'summary_text'
                                   or not isinstance(s.get('text'), str) for s in item['summary'])):
                        raise ValueError('Malformed reasoning item')
                    continue  # Retained in raw; never use reasoning as the scored answer.
                if not isinstance(item, dict) or item.get('type') != 'message' or item.get('role') != 'assistant' or item.get('status') != 'completed':
                    raise ValueError('Unexpected output item')
                if item.get('phase') not in (None, 'commentary', 'final_answer'):
                    raise ValueError('Unexpected message phase')
                if not isinstance(item.get('content'), list) or not item['content']:
                    raise ValueError('Missing content')
                for content in item['content']:
                    if not isinstance(content, dict) or content.get('type') != 'output_text' or not isinstance(content.get('text'), str):
                        raise ValueError('Unexpected output content')
                    if item.get('phase') != 'commentary':
                        texts.append(content['text'])
            if not texts or not ''.join(texts).strip():
                raise ValueError('Missing final text')
            return {'text': ''.join(texts), 'model': raw['model'],
                    'input_tokens': raw['usage']['input_tokens'], 'output_tokens': raw['usage']['output_tokens'],
                    'request_id': raw.get('_request_id') or raw.get('id'), 'stop_reason': 'end_turn', 'raw': raw}
        except ProviderError as exc:
            raise ProviderError(exc.code, raw=raw) from None
        except (KeyError, TypeError, ValueError):
            raise ProviderError('response_uncertain', raw=raw) from None
