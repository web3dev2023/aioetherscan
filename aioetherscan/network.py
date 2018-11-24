import asyncio
import logging
from enum import Enum
from typing import Union, Dict, List

import aiohttp
from asyncio_throttle import Throttler

from aioetherscan.exceptions import EtherscanClientContentTypeError, EtherscanClientError, EtherscanClientApiError, \
    EtherscanClientProxyError


class HttpMethod(Enum):
    GET = 'get'
    POST = 'post'


class Network:
    _BASE_URL = 'http://api.etherscan.io/api'

    def __init__(self, api_key: str, loop: asyncio.AbstractEventLoop) -> None:
        self._API_KEY = api_key

        self._loop = loop or asyncio.get_event_loop()
        self._session = aiohttp.ClientSession(loop=self._loop)
        self._throttler = Throttler(rate_limit=5)

        self._logger = logging.getLogger(__name__)

    async def close(self):
        await self._session.close()

    async def get(self, params: Dict = None) -> Union[Dict, List, str]:
        return await self._request(HttpMethod.GET, params=self._filter_and_sign(params))

    async def post(self, data: Dict = None) -> Union[Dict, List, str]:
        return await self._request(HttpMethod.POST, data=self._filter_and_sign(data))

    async def _request(self, method: HttpMethod, data: Dict = None, params: Dict = None) -> Union[Dict, List, str]:
        session_method = getattr(self._session, method.value)
        async with self._throttler:
            async with session_method(self._BASE_URL, params=params, data=data) as response:
                self._logger.debug('[%s] %r %r %s', method.name, str(response.url), data, response.status)
                return await self._handle_response(response)

    async def _handle_response(self, response: aiohttp.ClientResponse) -> Union[Dict, list, str]:
        try:
            response_json = await response.json()
        except aiohttp.ContentTypeError:
            raise EtherscanClientContentTypeError(response.status, await response.text())
        except Exception as e:
            raise EtherscanClientError(e)
        else:
            self._logger.debug('Response: %r', response_json)
            self._raise_if_error(response_json)
            return response_json['result']

    @staticmethod
    def _raise_if_error(response_json: Dict):
        if 'status' in response_json and response_json['status'] != '1':
            message, result = response_json.get('message'), response_json.get('result')
            raise EtherscanClientApiError(message, result)

        if 'error' in response_json:
            err = response_json['error']
            code, message = err.get('code'), err.get('message')
            raise EtherscanClientProxyError(code, message)

    def _filter_and_sign(self, params: Dict):
        return self._sign(
            self._filter_params(params or {})
        )

    def _sign(self, params: Dict) -> Dict:
        if not params:
            params = {}
        params['apikey'] = self._API_KEY
        return params

    @staticmethod
    def _filter_params(params: Dict) -> Dict:
        return {k: v for k, v in params.items() if v is not None}