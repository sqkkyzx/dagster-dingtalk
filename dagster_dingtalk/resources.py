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
    InitResourceContext, ResourceDependency,
)
from httpx import Client
from pydantic import Field, PrivateAttr


class DingTalkWebhookResource(ConfigurableResource):
    access_token: str = Field(description="Webhook地址中的 access_token 部分")
    secret: Optional[str] = Field(default=None, description="如使用加签安全配置，需传签名密钥")
    alias: Optional[str] = Field(default=None, description="如提供别名，将来可以使用别名进行选择")
    base_url: str = Field(default="https://oapi.dingtalk.com/robot/send", description="Webhook的通用地址，无需更改")

    def webhook_url(self):
        if self.secret is None:
            return f"{self.base_url}?access_token={self.access_token}"
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
        httpx.post(url=self.webhook_url(), json={"msgtype": "text", "text": {"content": text}, "at": at})

    def send_link(self, text: str, message_url:str, title:str|None = None, pic_url:str = ""):
        title = title or self._gen_title(text)
        httpx.post(
            url=self.webhook_url(),
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
        httpx.post(url=self.webhook_url(),json={"msgtype": "markdown", "markdown": {"title": title, "text": text}, "at": at})

    def send_action_card(self, text: List[str]|str, title:str|None = None, btn_orientation:Literal["0","1"] = "0",
                         single_jump:Tuple[str,str]|None = None, btns_jump:List[Tuple[str,str]]|None = None):
        text = text if isinstance(text, str) else "\n\n".join(text)
        title = title or self._gen_title(text)
        action_card = {"title": title, "text": text, "btnOrientation": btn_orientation}
        if btns_jump:
            action_card["btns"] = [{"title": action_title, "actionURL": action_url} for action_title, action_url in btns_jump]
            httpx.post(url=self.webhook_url(), json={"msgtype": "actionCard", "actionCard": action_card})
        elif single_jump:
            action_card["singleTitle"], action_card["singleURL"] = single_jump
            httpx.post(url=self.webhook_url(), json={"msgtype": "actionCard", "actionCard": action_card})
        else:
            pass

    def send_feed_card(self, links: List[Tuple[str,str,str]]):
        links_data = [
            {"title": title, "messageURL": message_url, "picURL": pic_url}
            for title, message_url, pic_url in links
        ]
        httpx.post(url=self.webhook_url(), json={"msgtype": "feedCard", "feedCard": {"links": links_data}})


# noinspection NonAsciiCharacters
class MultiDingTalkWebhookResource(ConfigurableResource):
    """
    该资源提供了预先定义多个 webhook 资源，并在运行时动态选择的方法。

    使用示例：

    ```
    from dagster_dingtalk import DingTalkResource, MultiDingTalkResource

    app_apple = DingTalkResource(AppID="apple", ClientId="", ClientSecret="")
    app_book = DingTalkResource(AppID="book", ClientId="", ClientSecret="")

    @op(required_resource_keys={"dingtalk"}, ins={"app_id":In(str)})
    def print_app_id(context:OpExecutionContext, app_id):
        dingtalk:DingTalkResource = context.resources.dingtalk
        select_app = dingtalk.select_app(app_id)
        context.log.info(dingtalk_app.AppName)

    @job
    def print_app_id_job():
        print_app_id()

    defs = Definitions(
        jobs=[print_app_id_job],
        resources={
            "dingtalk": MultiDingTalkResource(
                Apps=[app_apple, app_book]
            )
        },
    )
    ```

    """

    Webhooks: ResourceDependency[List[DingTalkWebhookResource]] = Field(description="多个 Webhook 资源的列表")

    _webhooks = PrivateAttr()

    def setup_for_execution(self, context: InitResourceContext) -> None:
        _webhooks_token_key = {webhook.access_token:webhook for webhook in self.Webhooks}
        _webhooks_alias_key = {webhook.alias:webhook for webhook in self.Webhooks if webhook.alias}
        self._webhooks = _webhooks_token_key | _webhooks_alias_key

    def select(self, key:str = "_FIRST_"):
        try:
            if key == "_FIRST_" or key is None:
                webhook = self.Webhooks[0]
            else:
                webhook = self._webhooks[key]
            webhook.init_webhook_url()
            return webhook
        except KeyError:
            raise f"该 AccessToken 或 别名 <{key}> 不存在于提供的 Webhooks 中。请使用 DingTalkWebhookResource 定义单个 Webhook 后，将其加入 Webhooks 。"


class DingTalkClient:
    def __init__(self, access_token: str, app_id: str, agent_id: int, robot_code: str) -> None:
        self.access_token: str = access_token
        self.app_id: str = app_id
        self.agent_id: int = agent_id
        self.robot_code: str = robot_code
        self.api: Client = httpx.Client(base_url="https://api.dingtalk.com/", headers={"x-acs-dingtalk-access-token": self.access_token})
        self.oapi: Client = httpx.Client(base_url="https://oapi.dingtalk.com/", params={"access_token": self.access_token})


# noinspection NonAsciiCharacters
class DingTalkResource(ConfigurableResource):
    """
    [钉钉服务端 API](https://open.dingtalk.com/document/orgapp/api-overview) 企业内部应用部分的第三方封装。
    通过此资源，可以调用部分钉钉服务端API。

    注意：不包含全部的API端点。
    """

    AppID: str = Field(description="应用应用唯一标识 AppID，作为缓存标识符使用。不传入则不缓存鉴权。")
    AgentID: Optional[int] = Field(default=None, description="原企业内部应用AgentId ，部分API会使用到。")
    AppName: Optional[str] = Field(default=None, description="应用名。")
    ClientId: str = Field(description="应用的 Client ID (原 AppKey 和 SuiteKey)")
    ClientSecret: str = Field(description="应用的 Client Secret (原 AppSecret 和 SuiteSecret)")
    RobotCode: Optional[str] = Field(default=None, description="应用的机器人 RobotCode，不传时使用 self.ClientId ")

    _client: DingTalkClient = PrivateAttr()

    @classmethod
    def _is_dagster_maintained(cls) -> bool:
        return False

    def _get_access_token(self) -> str:
        access_token_cache = Path("/tmp/.dingtalk_cache")

        try:
            with open(access_token_cache, 'rb') as f:
                all_access_token: Dict[str, Tuple[str, int]] = pickle.loads(f.read())
                access_token, expire_in = all_access_token.get(self.AppID, ('', 0))
        except Exception as e:
            print(e)
            all_access_token = {}
            access_token, expire_in = all_access_token.get(self.AppID, ('', 0))

        if access_token and expire_in < int(time.time()):
            return access_token
        else:
            print(f"应用{self.AppName}<{self.AppID}> 鉴权缓存过期或不存在，正在重新获取...")
            response = httpx.post(
                url="https://api.dingtalk.com/v1.0/oauth2/accessToken",
                json={"appKey": self.ClientId, "appSecret": self.ClientSecret},
            )
            access_token:str = response.json().get("accessToken")
            expire_in:int = response.json().get("expireIn") + int(time.time()) - 60
            with open(access_token_cache, 'wb') as f:
                all_access_token[self.AppID] = (access_token, expire_in)
                f.write(pickle.dumps(all_access_token))
            return access_token

    def init_client(self):
        if not hasattr(self, '_client'):
            self._client = DingTalkClient(
                self._get_access_token(),
                self.AppID,
                self.AgentID,
                self.RobotCode or self.ClientId
            )

    def setup_for_execution(self, context: InitResourceContext) -> None:
        self.init_client()

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
class MultiDingTalkResource(ConfigurableResource):
    """
    该资源提供了预先定义多个应用资源，并在运行时动态选择的方法。

    使用示例：

    ```
    from dagster_dingtalk import DingTalkResource, MultiDingTalkResource

    app_apple = DingTalkResource(AppID="apple", ClientId="", ClientSecret="")
    app_book = DingTalkResource(AppID="book", ClientId="", ClientSecret="")

    @op(required_resource_keys={"dingtalk"}, ins={"app_id":In(str)})
    def print_app_id(context:OpExecutionContext, app_id):
        dingtalk:DingTalkResource = context.resources.dingtalk
        select_app = dingtalk.select_app(app_id)
        context.log.info(dingtalk_app.AppName)

    @job
    def print_app_id_job():
        print_app_id()

    defs = Definitions(
        jobs=[print_app_id_job],
        resources={
            "dingtalk": MultiDingTalkResource(
                Apps=[app_apple, app_book]
            )
        },
    )
    ```

    """

    Apps: ResourceDependency[List[DingTalkResource]] = Field(description="多个单应用资源的列表")

    _apps = PrivateAttr()

    def setup_for_execution(self, context: InitResourceContext) -> None:
        self._apps = {app.AppID:app for app in self.Apps}

    def select(self, app_id:str = "_FIRST_"):
        try:
            if app_id == "_FIRST_" or app_id is None:
                app = self.Apps[0]
            else:
                app = self._apps[app_id]
            app.init_client()
            return app
        except KeyError:
            raise f"该 AppID <{app_id}> 不存在于提供的 AppLists 中。请使用 DingTalkResource 定义单个 App 后，将其加入 AppLists 。"


# noinspection NonAsciiCharacters
class API_智能人事:
    def __init__(self, _client:DingTalkClient):
        self._client = _client

    def 花名册_获取花名册元数据(self) -> dict:
        response = self._client.oapi.post(
            url="/topapi/smartwork/hrm/roster/meta/get",
            json={"agentid": self._client.agent_id},
        )
        return response.json()

    def 花名册_获取员工花名册字段信息(self, user_id_list:List[str], field_filter_list:List[str]|None = None, text_to_select_convert:bool|None = None) -> dict:
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

    def 员工管理_获取待入职员工列表(self, offset:int, size:int) -> dict:
        response = self._client.oapi.post(
            "/topapi/smartwork/hrm/employee/querypreentry",
            json={"offset": offset, "size": size},
        )
        return response.json()

    def 员工管理_获取在职员工列表(self, status_list:List[在职员工状态], offset:int, size:int) -> dict:
        response = self._client.oapi.post(
            "/topapi/smartwork/hrm/employee/querypreentry",
            json={"status_list": status_list, "offset": offset, "size": size},
        )
        return response.json()

    def 员工管理_获取离职员工列表(self, next_token:int, max_results:int) -> dict:
        response = self._client.api.get(
            "/v1.0/hrm/employees/dismissions",
            params={"nextToken": next_token, "maxResults": max_results},
        )
        return response.json()

    def 员工管理_批量获取员工离职信息(self, user_id_list:List[str]) -> dict:
        response = self._client.api.get(
            "/v1.0/hrm/employees/dimissionInfo",
            params={"userIdList": user_id_list},
        )
        return response.json()


# noinspection NonAsciiCharacters
class API_通讯录管理:
    def __init__(self, _client:DingTalkClient):
        self._client = _client

    def 查询用户详情(self, user_id:str, language:str = "zh_CN") -> dict:
        response = self._client.oapi.post(url="/topapi/v2/user/get", json={"language": language, "userid": user_id})
        return response.json()

    def 查询离职记录列表(self, start_time:datetime, end_time:datetime|None, next_token:str, max_results:int) -> dict:
        params = {"startTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"), "nextToken": next_token, "maxResults": max_results}
        if end_time is not None:
            params["endTime"] = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        response = self._client.api.get(url="/v1.0/contact/empLeaveRecords", params=params)
        return response.json()


# noinspection NonAsciiCharacters
class API_文档文件:
    def __init__(self, _client:DingTalkClient):
        self._client = _client

    def 媒体文件_上传媒体文件(self, file_path:Path|str, media_type:Literal['image', 'voice', 'video', 'file']) -> dict:
        with open(file_path, 'rb') as f:
            response = self._client.oapi.post(url=f"/media/upload?type={media_type}", files={'media': f})
        return response.json()

