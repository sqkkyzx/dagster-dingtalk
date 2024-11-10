import base64
import hashlib
import hmac
import time
import urllib.parse
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Tuple, List, Literal
import pickle
import httpx

from dagster import (
    ConfigurableResource,
    InitResourceContext,
)
from httpx import Client
from pydantic import Field, PrivateAttr


class DingTalkWebhookResource(ConfigurableResource):
    base_url: str = Field(default="https://oapi.dingtalk.com/robot/send", description="Webhook的通用地址，无需更改")
    access_token: str = Field(description="Webhook地址中的 access_token 部分")
    secret: Optional[str] = Field(default=None, description="如使用加签安全配置，需传签名密钥")

    def _sign_webhook_url(self):

        if self.secret is None:
            return self.webhook_url
        else:
            timestamp = round(time.time() * 1000)
            hmac_code = hmac.new(
                self.secret.encode('utf-8'), f'{timestamp}\n{self.secret}'.encode('utf-8'), digestmod=hashlib.sha256
            ).digest()
            sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
            return f"{self.base_url}?access_token={self.access_token}&timestamp={timestamp}&sign={sign}"

    @staticmethod
    def _gen_title(text):
        return text[:12].replace("\n", "").replace("#", "").replace(">", "").replace("*", "")

    def send_text(self, text: str,
                  at_mobiles:List[str]|None = None, at_user_ids:List[str]|None = None, at_all:bool = False):
        at = {"isAtAll": at_all}
        if at_user_ids:
            at["atUserIds"] = at_user_ids
        if at_mobiles:
            at["atMobiles"] = at_mobiles
        httpx.post(url=self.webhook_url, json={"msgtype": "text", "text": {"content": text}, "at": at})

    def send_link(self, text: str, message_url:str, title:str|None = None, pic_url:str = ""):
        title = title or self._gen_title(text)
        httpx.post(
            url=self.webhook_url,
            json={"msgtype": "link", "link": {"title": title, "text": text, "picUrl": pic_url, "messageUrl": message_url}}
        )

    def send_markdown(self, text: List[str]|str, title:str|None = None,
                      at_mobiles:List[str]|None = None, at_user_ids:List[str]|None = None, at_all:bool = False):
        text = text if isinstance(text, str) else "\n\n".join(text)
        title = title or self._gen_title(text)
        at = {"isAtAll": at_all}
        if at_user_ids:
            at["atUserIds"] = at_user_ids
        if at_mobiles:
            at["atMobiles"] = at_mobiles
        httpx.post(url=self.webhook_url,json={"msgtype": "markdown", "markdown": {"title": title, "text": text}, "at": at})

    def send_action_card(self, text: List[str]|str, title:str|None = None, btn_orientation:Literal["0","1"] = "0",
                         single_jump:Tuple[str,str]|None = None, btns_jump:List[Tuple[str,str]]|None = None):
        text = text if isinstance(text, str) else "\n\n".join(text)
        title = title or self._gen_title(text)
        action_card = {"title": title, "text": text, "btnOrientation": btn_orientation}
        if btns_jump:
            action_card["btns"] = [{"title": action_title, "actionURL": action_url} for action_title, action_url in btns_jump]
            httpx.post(url=self.webhook_url, json={"msgtype": "actionCard", "actionCard": action_card})
        elif single_jump:
            action_card["singleTitle"], action_card["singleURL"] = single_jump
            httpx.post(url=self.webhook_url, json={"msgtype": "actionCard", "actionCard": action_card})
        else:
            pass

    def send_feed_card(self, links: List[Tuple[str,str,str]]):
        links_data = [
            {"title": title, "messageURL": message_url, "picURL": pic_url}
            for title, message_url, pic_url in links
        ]
        httpx.post(url=self.webhook_url, json={"msgtype": "feedCard", "feedCard": {"links": links_data}})


class DingTalkMultiClient:
    def __init__(self, access_token: str, app_id: str, agent_id: int, robot_code: str) -> None:
        self.access_token: str = access_token
        self.app_id: str = app_id
        self.agent_id: int = agent_id
        self.robot_code: str = robot_code
        self.api: Client = httpx.Client(base_url="https://api.dingtalk.com/", headers={"x-acs-dingtalk-access-token": self.access_token})
        self.oapi: Client = httpx.Client(base_url="https://oapi.dingtalk.com/", params={"access_token": self.access_token})


# noinspection NonAsciiCharacters
class DingTalkAPIResource(ConfigurableResource):
    """
    [钉钉服务端 API](https://open.dingtalk.com/document/orgapp/api-overview) 企业内部应用部分的第三方封装。
    通过此资源，可以调用部分钉钉服务端API。

    注意：不包含全部的API端点。
    """

    AppID: Optional[str] = Field(default=None, description="应用应用唯一标识 AppID，作为缓存标识符使用。不传入则不缓存鉴权。")
    AgentID: Optional[int] = Field(default=None, description="原企业内部应用AgentId ，部分API会使用到。")
    AppName: Optional[str] = Field(default=None, description="应用名。")
    ClientId: str = Field(description="应用的 Client ID (原 AppKey 和 SuiteKey)")
    ClientSecret: str = Field(description="应用的 Client Secret (原 AppSecret 和 SuiteSecret)")
    RobotCode: str = Field(description="应用的机器人 RobotCode")

    _client: DingTalkMultiClient = PrivateAttr()

    @classmethod
    def _is_dagster_maintained(cls) -> bool:
        return False

    def _get_access_token(self, context: InitResourceContext) -> str:
        access_token_cache = Path("~/.dingtalk_cache")

        if access_token_cache.exists():
            with open(access_token_cache, 'rb') as f:
                all_access_token: Dict[str, Tuple[str, int]] = pickle.loads(f.read())
        else:
            all_access_token = {}

        access_token, expire_in = all_access_token.get(self.AppID, ('', 0))

        if access_token and expire_in < int(time.time()):
            return access_token
        else:
            context.log.info(f"应用{self.AppName}<{self.AppID}> 鉴权缓存过期或不存在，正在重新获取...")
            response = httpx.post(
                url="https://api.dingtalk.com/v1.0/oauth2/accessToken",
                json={"appKey": self.ClientId, "appSecret": self.ClientSecret},
            )
            access_token:str = response.json().get("accessToken")
            expire_in:int = response.json().get("expireIn") + int(time.time()) - 60
            with open(access_token_cache, 'wb') as f:
                all_access_token[self.AppID] = (access_token, expire_in)
                f.write(pickle.dumps(access_token_cache))
            return access_token

    def setup_for_execution(self, context: InitResourceContext) -> None:
        self._client = DingTalkMultiClient(
            self._get_access_token(context),
            self.AppID,
            self.AgentID,
            self.RobotCode,
        )

    def teardown_after_execution(self, context: InitResourceContext) -> None:
        self._client.api.close()
        self._client.oapi.close()

    def 智能人事(self):
        return API_智能人事(self._client)

    def 通讯录管理(self):
        return API_通讯录管理(self._client)

    def 文档文件(self):
        return API_文档文件(self._client)


# noinspection NonAsciiCharacters
class API_智能人事:
    def __init__(self, _client:DingTalkMultiClient):
        self._client = _client

    def 花名册_获取花名册元数据(self):
        response = self._client.oapi.post(
            url="/topapi/smartwork/hrm/roster/meta/get",
            json={"agentid": self._client.agent_id},
        )
        return response.json()

    def 花名册_获取员工花名册字段信息(self, user_id_list:List[str], field_filter_list:List[str]|None = None, text_to_select_convert:bool|None = None):
        body_dict = {"userIdList": user_id_list, "appAgentId": self._client.agent_id}
        if field_filter_list is not None:
            body_dict["fieldFilterList"] = field_filter_list
        if text_to_select_convert is not None:
            body_dict["text2SelectConvert"] = text_to_select_convert

        response = self._client.api.post(url="/topapi/smartwork/hrm/roster/meta/get", json=body_dict,)
        return response.json()

    # noinspection NonAsciiCharacters
    class 在职员工状态(Enum):
        试用期: '2'
        正式: '3'
        待离职: '5'
        无状态: '-1'

    def 员工管理_获取待入职员工列表(self, offset:int, size:int):
        response = self._client.oapi.post(
            "/topapi/smartwork/hrm/employee/querypreentry",
            json={"offset": offset, "size": size},
        )
        return response.json()

    def 员工管理_获取在职员工列表(self, status_list:List[在职员工状态], offset:int, size:int):
        response = self._client.oapi.post(
            "/topapi/smartwork/hrm/employee/querypreentry",
            json={"status_list": status_list, "offset": offset, "size": size},
        )
        return response.json()

    def 员工管理_获取离职员工列表(self, next_token:int, max_results:int):
        response = self._client.api.get(
            "/v1.0/hrm/employees/dismissions",
            params={"nextToken": next_token, "maxResults": max_results},
        )
        return response.json()

    def 员工管理_批量获取员工离职信息(self, user_id_list:List[str]):
        response = self._client.api.get(
            "/v1.0/hrm/employees/dimissionInfo",
            params={"userIdList": user_id_list},
        )
        return response.json()


# noinspection NonAsciiCharacters
class API_通讯录管理:
    def __init__(self, _client:DingTalkMultiClient):
        self._client = _client

    def 查询用户详情(self, user_id:str, language:str = "zh_CN"):
        response = self._client.oapi.post(url="/topapi/v2/user/get", json={"language": language, "userid": user_id})
        return response.json()

    def 查询离职记录列表(self, start_time:datetime, end_time:datetime|None, next_token:str, max_results:int):
        params = {"startTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"), "nextToken": next_token, "maxResults": max_results}
        if end_time is not None:
            params["endTime"] = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        response = self._client.api.get(url="/v1.0/contact/empLeaveRecords", params=params)
        return response.json()


# noinspection NonAsciiCharacters
class API_文档文件:
    def __init__(self, _client:DingTalkMultiClient):
        self._client = _client

    def 媒体文件_上传媒体文件(self, file_path:Path|str, media_type:Literal['image', 'voice', 'video', 'file']):
        with open(file_path, 'rb') as f:
            response = self._client.oapi.post(url=f"/media/upload?type={media_type}", files={'media': f})
        return response.json()

