import logging
import pickle
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Literal, Dict, Tuple
from httpx import Client


# noinspection NonAsciiCharacters
class DingTalkClient:
    def __init__(self, app_id: str, client_id: str, client_secret: str, app_name: str|None = None, agent_id: int|None = None):
        self.app_id: str = app_id
        self.app_name: str|None = app_name
        self.agent_id: int|None = agent_id
        self.client_id: str = client_id
        self.__client_secret: str = client_secret
        self.robot_code: str = client_id

        access_token: str = self._get_access_token()
        self.api: Client = Client(base_url="https://api.dingtalk.com/", headers={"x-acs-dingtalk-access-token": access_token})
        self.oapi: Client = Client(base_url="https://oapi.dingtalk.com/", params={"access_token": access_token})

        self.智能人事 = 智能人事_API(self)
        self.通讯录管理 = 通讯录管理_API(self)
        self.文档文件 = 文档文件_API(self)

    def _get_access_token(self) -> str:
        access_token_cache = Path("/tmp/.dingtalk_cache")

        try:
            with open(access_token_cache, 'rb') as f:
                all_access_token: Dict[str, Tuple[str, int]] = pickle.loads(f.read())
                access_token, expire_in = all_access_token.get(self.app_id, ('', 0))
        except Exception as e:
            print(e)
            all_access_token = {}
            access_token, expire_in = all_access_token.get(self.app_id, ('', 0))

        if access_token and expire_in < int(time.time()):
            return access_token
        else:
            logging.warning(f"应用{self.app_name}<{self.app_id}> 鉴权缓存过期或不存在，正在重新获取...")
            response = Client().post(
                url="https://api.dingtalk.com/v1.0/oauth2/accessToken",
                json={"appKey": self.client_id, "appSecret": self.__client_secret},
            )
            access_token:str = response.json().get("accessToken")
            expire_in:int = response.json().get("expireIn") + int(time.time()) - 60
            with open(access_token_cache, 'wb') as f:
                all_access_token[self.app_id] = (access_token, expire_in)
                f.write(pickle.dumps(all_access_token))
            return access_token

# noinspection NonAsciiCharacters
class 智能人事_API:
    def __init__(self, _client:DingTalkClient):
        self.花名册 = 智能人事_花名册_API(_client)
        self.员工管理 = 智能人事_员工管理_API(_client)

# noinspection NonAsciiCharacters
class 智能人事_花名册_API:
    def __init__(self, _client:DingTalkClient):
        self.__client:DingTalkClient = _client

    def 获取花名册元数据(self) -> dict:
        response = self.__client.oapi.post(
            url="/topapi/smartwork/hrm/roster/meta/get",
            json={"agentid": self.__client.agent_id},
        )
        return response.json()

    def 获取员工花名册字段信息(self, user_id_list:List[str], field_filter_list:List[str]|None = None, text_to_select_convert:bool|None = None) -> dict:
        body_dict = {"userIdList": user_id_list, "appAgentId": self.__client.agent_id}
        if field_filter_list is not None:
            body_dict["fieldFilterList"] = field_filter_list
        if text_to_select_convert is not None:
            body_dict["text2SelectConvert"] = text_to_select_convert

        response = self.__client.api.post(url="/topapi/smartwork/hrm/roster/meta/get", json=body_dict, )
        return response.json()

# noinspection NonAsciiCharacters
class 智能人事_员工管理_API:

    def __init__(self, _client:DingTalkClient):
        self.__client:DingTalkClient = _client

    # noinspection NonAsciiCharacters
    class 在职员工状态(Enum):
        试用期: '2'
        正式: '3'
        待离职: '5'
        无状态: '-1'

    def 获取待入职员工列表(self, offset:int, size:int) -> dict:
        response = self.__client.oapi.post(
            "/topapi/smartwork/hrm/employee/querypreentry",
            json={"offset": offset, "size": size},
        )
        return response.json()

    def 获取在职员工列表(self, status_list:List[在职员工状态], offset:int, size:int) -> dict:
        response = self.__client.oapi.post(
            "/topapi/smartwork/hrm/employee/querypreentry",
            json={"status_list": status_list, "offset": offset, "size": size},
        )
        return response.json()

    def 获取离职员工列表(self, next_token:int, max_results:int) -> dict:
        response = self.__client.api.get(
            "/v1.0/hrm/employees/dismissions",
            params={"nextToken": next_token, "maxResults": max_results},
        )
        return response.json()

    def 批量获取员工离职信息(self, user_id_list:List[str]) -> dict:
        response = self.__client.api.get(
            "/v1.0/hrm/employees/dimissionInfo",
            params={"userIdList": user_id_list},
        )
        return response.json()

# noinspection NonAsciiCharacters
class 通讯录管理_API:
    def __init__(self, _client:DingTalkClient):
        self.__client = _client

    def 查询用户详情(self, user_id:str, language:str = "zh_CN") -> dict:
        response = self.__client.oapi.post(url="/topapi/v2/user/get", json={"language": language, "userid": user_id})
        return response.json()

    def 查询离职记录列表(self, start_time:datetime, end_time:datetime|None, next_token:str, max_results:int) -> dict:
        params = {"startTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"), "nextToken": next_token, "maxResults": max_results}
        if end_time is not None:
            params["endTime"] = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        response = self.__client.api.get(url="/v1.0/contact/empLeaveRecords", params=params)
        return response.json()

# noinspection NonAsciiCharacters
class 文档文件_API:
    def __init__(self, _client:DingTalkClient):
        self.媒体文件 = 文档文件_媒体文件_API(_client)

# noinspection NonAsciiCharacters
class 文档文件_媒体文件_API:
    def __init__(self, _client:DingTalkClient):
        self.__client = _client

    def 上传媒体文件(self, file_path:Path|str, media_type:Literal['image', 'voice', 'video', 'file']) -> dict:
        with open(file_path, 'rb') as f:
            response = self.__client.oapi.post(url=f"/media/upload?type={media_type}", files={'media': f})
        return response.json()
