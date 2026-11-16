"""Provider boundary. No SDK retries, hidden tool calls, caching or credentials on disk."""
import base64
import json
import math
import os
import re
import socket
from typing import Protocol
import urllib.error
import urllib.request


class ProviderError(Exception):
    def __init__(self, code, retryable=False, retry_after=0, raw=None):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after
        self.raw = raw


class Provider(Protocol):
    name: str
    def count_tokens(self, request: dict) -> int: ...
    def generate(self, request: dict) -> dict: ...


class MockProvider:
    name = 'mock'

    def count_tokens(self, request):
        return len(request['prompt'].encode('utf-8'))

    def generate(self, request):
        match = re.search(r'What is (\d+) \+ (\d+)\?', request['prompt'])
        answer = str(int(match[1]) + int(match[2])) if match else 'MOCK: no arithmetic fixture found'
        return {'text': answer, 'model': 'mock-v1', 'input_tokens': self.count_tokens(request),
                'output_tokens': len(answer), 'request_id': None, 'stop_reason': 'end_turn',
                'raw': {'synthetic': True, 'answer': answer}}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward an API key through a redirect.


def http_post(path, payload, key, timeout, version):
    request = urllib.request.Request('https://api.anthropic.com/v1/' + path,
        data=json.dumps(payload, allow_nan=False).encode('utf-8'), method='POST',
        headers={'Content-Type': 'application/json', 'x-api-key': key,
                 'anthropic-version': version})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
            body = response.read()
            try:
                document = json.loads(body)
            except (ValueError, UnicodeError):
                raise ProviderError('response_uncertain', raw={'body_base64': base64.b64encode(body).decode('ascii'),
                                                             'request_id': response.headers.get('request-id')}) from None
            if not isinstance(document, dict):
                raise ProviderError('response_uncertain', raw=document)
            document['_request_id'] = response.headers.get('request-id')
            return document
    except urllib.error.HTTPError as exc:
        try:
            retry_after = float(exc.headers.get('retry-after', 0))
            if not math.isfinite(retry_after) or retry_after < 0:
                retry_after = 0
        except (ValueError, TypeError):
            retry_after = 0
        raise ProviderError(f'http_{exc.code}', retryable=exc.code in (408, 409, 429, 500, 502, 503, 504, 529),
                            retry_after=retry_after) from None
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
        # A transport error may have occurred AFTER the provider accepted the request.
        raise ProviderError('transport_uncertain') from None
    except (ValueError, TypeError):
        raise ProviderError('response_uncertain') from None


def valid_tokens(value):
    if type(value) is not int or value < 0:
        raise ProviderError('invalid_usage_uncertain')
    return value


class AnthropicProvider:
    name = 'anthropic'

    def __init__(self, post=None):
        self._key = os.environ.get('ANTHROPIC_API_KEY')
        if not self._key:
            raise ValueError('Set ANTHROPIC_API_KEY in this process environment for live runs')
        self._post = post or http_post

    def _call(self, path, payload, request):
        return self._post(path, payload, self._key, request['timeout_seconds'], request['api_version'])

    def _payload(self, request):
        return {'model': request['model'], 'messages': [{'role': 'user', 'content': request['prompt']}]}

    def count_tokens(self, request):
        result = self._call('messages/count_tokens', self._payload(request), request)
        if not isinstance(result, dict):
            raise ProviderError('response_uncertain', raw=result)
        return valid_tokens(result.get('input_tokens'))

    def generate(self, request):
        payload = dict(self._payload(request), max_tokens=request['max_output_tokens'],
                       temperature=request['temperature'])
        raw = self._call('messages', payload, request)
        try:
            content = raw['content']
            if not isinstance(content, list) or not content or any(
                    not isinstance(c, dict) or c.get('type') != 'text' or not isinstance(c.get('text'), str)
                    for c in content):
                raise ValueError('Unsupported response content')
            return {'text': ''.join(c['text'] for c in content), 'model': raw['model'],
                    'input_tokens': valid_tokens(raw['usage']['input_tokens']),
                    'output_tokens': valid_tokens(raw['usage']['output_tokens']),
                    'request_id': raw.get('_request_id', raw.get('id')),
                    'stop_reason': raw['stop_reason'], 'raw': raw}
        except (KeyError, TypeError, ValueError, ProviderError):
            raise ProviderError('response_uncertain', raw=raw) from None
