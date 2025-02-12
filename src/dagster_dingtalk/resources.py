import base64
import hashlib
import hmac
import re
import time
import urllib.parse
from typing import Optional, Tuple, List, Literal
import httpx
from pydantic import Field
from .app_client import DingTalkClient
from dagster import ConfigurableResource, InitResourceContext


DINGTALK_WEBHOOK_EXCEPTION_SOLUTIONS = {
    "-1": "\n系统繁忙，请稍后重试",
    "40035": "\n缺少参数 json，请补充消息json",
    "43004": "\n无效的HTTP HEADER Content-Type，请设置具体的消息参数",
    "400013": "\n群已被解散，请向其他群发消息",
    "400101": "\naccess_token不存在，请确认access_token拼写是否正确",
    "400102": "\n机器人已停用，请联系管理员启用机器人",
    "400105": "\n不支持的消息类型，请使用文档中支持的消息类型",
    "400106": "\n机器人不存在，请确认机器人是否在群中",
    "410100": "\n发送速度太快而限流，请降低发送速度",
    "430101": "\n含有不安全的外链，请确认发送的内容合法",
    "430102": "\n含有不合适的文本，请确认发送的内容合法",
    "430103": "\n含有不合适的图片，请确认发送的内容合法",
    "430104": "\n含有不合适的内容，请确认发送的内容合法",
    "310000": "\n消息校验未通过，请查看机器人的安全设置",
}


class DingTalkWebhookException(Exception):
    def __init__(self, errcode, errmsg):
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"DingTalkWebhookError {errcode}: {errmsg} {DINGTALK_WEBHOOK_EXCEPTION_SOLUTIONS.get(errcode)}")


class DingTalkWebhookResource(ConfigurableResource):
    """
    该资源允许定义单个钉钉自定义机器人的 Webhook 端点，以便于发送文本、Markdown、Link、 ActionCard、FeedCard 消息，消息具体样式可参考
    [钉钉开放平台 | 自定义机器人发送消息的消息类型](https://open.dingtalk.com/document/orgapp/custom-bot-send-message-type)。

    ### 配置项:

    - **access_token** (str):
            机器人 Webhook 地址中的 access_token 值。
    - **secret** (str, optional):
        如使用加签安全配置，则需传签名密钥。默认值为 None。
    - **alias** (str, optional):
        别名，仅用作标记。默认值为 None。
    - **base_url** (str, optional):
        通用地址，一般无需更改。默认值为 “https://oapi.dingtalk.com/robot/send”。

    ### 用例:

    ##### 1. 使用单个资源：
    ```python
    from dagster_dingtalk import DingTalkWebhookResource
    from dagster import op, In, OpExecutionContext, job, Definitions

    @op(required_resource_keys={"dingtalk_webhook"}, ins={"text": In(str)})
    def op_send_text(context:OpExecutionContext, text:str):
        dingtalk_webhook:DingTalkWebhookResource = context.resources.dingtalk_webhook
        dingtalk_webhook.send_text(text)

    @job
    def job_send_text():
        op_send_text()

    defs = Definitions(
        jobs=[job_send_text],
        resources={"dingtalk_webhook": DingTalkWebhookResource(access_token = "<access_token>", secret = "<secret>")}
    )
    ```

    ##### 2. 启动时动态构建企业内部应用资源, 可参考 [Dagster文档 | 在启动时配置资源](https://docs.dagster.io/concepts/resources#configuring-resources-at-launch-time)

    ```python
    from dagster_dingtalk import DingTalkWebhookResource
    from dagster import op, In, OpExecutionContext, job, Definitions, schedule, RunRequest, RunConfig

    @op(required_resource_keys={"dingtalk_webhook"}, ins={"text": In(str)})
    def op_send_text(context:OpExecutionContext, text:str):
        dingtalk_webhook:DingTalkWebhookResource = context.resources.dingtalk_webhook
        dingtalk_webhook.send_text(text)

    @job
    def job_send_text():
        op_send_text()

    dingtalk_webhooks = {
        "Group1" : DingTalkWebhookResource(access_token="<access_token>", secret="<secret>", alias="Group1"),
        "Group2" : DingTalkWebhookResource(access_token="<access_token>", secret="<secret>", alias="Group2")
    }

    defs = Definitions(
        jobs=[job_send_text],
        resources={"dingtalk_webhook": DingTalkWebhookResource.configure_at_launch()}
    )

    @schedule(cron_schedule="20 9 * * *", job=job_send_text)
    def schedule_user_info():
        return RunRequest(run_config=RunConfig(
            ops={"op_send_text": {"inputs": {"text": "This a test text."}}},
            resources={"dingtalk": dingtalk_webhooks["Group1"]},
        ))
    ```

    ### 注意:

    应该永远避免直接将密钥字符串直接配置给资源，这会导致在 dagster 前端用户界面暴露密钥。
    应当从环境变量中读取密钥。你可以在代码中注册临时的环境变量，或从系统中引入环境变量。

    ```python

    import os
    from dagster import EnvVar
    from dagster_dingtalk import DingTalkWebhookResource

    # 直接在代码中注册临时的环境变量
    os.environ.update({'access_token_name': "<your-access_token>"})
    os.environ.update({'secret_name': "<your-secret>"})

    webhook = DingTalkWebhookResource(access_token=EnvVar("access_token_name"), secret=EnvVar("secret_name"))
    ```
    """

    access_token: str = Field(description="Webhook地址中的 access_token 部分")
    secret: Optional[str] = Field(default=None, description="如使用加签安全配置，需传签名密钥")
    alias: Optional[str] = Field(default=None, description="别名，标记用，无实际意义")
    base_url: str = Field(default="https://oapi.dingtalk.com/robot/send", description="Webhook的通用地址，无需更改")

    def webhook_url(self):
        """
        实时生成加签或未加签的 Webhook URL。

        钉钉API文档：
        https://open.dingtalk.com/document/robots/custom-robot-access

        :return:
            str: Webhook URL
        """
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
        """
        从文本截取前12个字符作为标题，并清理其中的 Markdown 格式字符。

        :param text: 原文

        :return:
            str: 标题
        """
        return re.sub(r'[\n#>* ]', '', text[:12])

    @staticmethod
    def __handle_response(response):
        """
        处理钉钉 Webhook API 响应，根据 errcode 抛出相应的异常

        :param response: 钉钉Webhook API响应的JSON数据
        """
        errcode = str(response.json().get("errcode"))
        errmsg = response.json().get("errmsg")

        if errcode == "0":
            return True
        else:
            raise DingTalkWebhookException(errcode, errmsg)

    def send_text(self, text: str,
                  at_mobiles:List[str]|None = None, at_user_ids:List[str]|None = None, at_all:bool = False):
        """
        发送文本消息。

        钉钉API文档：
        https://open.dingtalk.com/document/orgapp/custom-bot-send-message-type

        :param str text: 待发送文本
        :param List[str],optional at_mobiles: 需要 @ 的用户手机号。默认值为 None
        :param List[str],optional at_user_ids: 需要 @ 的用户 UserID。默认值为 None
        :param bool,optional at_all: 是否 @ 所有人。默认值为 False

        :raise DingTalkWebhookException:

        """
        at = {"isAtAll": at_all}
        if at_user_ids:
            at["atUserIds"] = at_user_ids
        if at_mobiles:
            at["atMobiles"] = at_mobiles
        response = httpx.post(url=self.webhook_url(), json={"msgtype": "text", "text": {"content": text}, "at": at})
        self.__handle_response(response)

    def send_link(self, text: str, message_url:str, title:str|None = None, pic_url:str = ""):
        """
        发送 Link 消息。

        钉钉API文档：
        https://open.dingtalk.com/document/orgapp/custom-bot-send-message-type

        :param str text: 待发送文本
        :param str message_url: 链接的 Url
        :param str,optional title: 标题，在通知和被引用时显示的简短信息。默认从文本中生成。
        :param str,optional pic_url: 图片的 Url，默认为 None

        :raise DingTalkWebhookException:
        """
        title = title or self._gen_title(text)
        response = httpx.post(
            url=self.webhook_url(),
            json={"msgtype": "link", "link": {"title": title, "text": text, "picUrl": pic_url, "messageUrl": message_url}}
        )
        self.__handle_response(response)

    def send_markdown(self, text: List[str]|str, title:str|None = None,
                      at_mobiles:List[str]|None = None, at_user_ids:List[str]|None = None, at_all:bool = False):
        """
        发送 Markdown 消息。支持的语法有：
            # 一级标题  ## 二级标题  ### 三级标题  #### 四级标题  ##### 五级标题  ###### 六级标题
            > 引用  **加粗**  *斜体*
            [链接跳转](https://example.com/doc.html)
            ![图片预览](https://example.com/pic.jpg)
            - 无序列表
            1. 有序列表

        钉钉API文档：
        https://open.dingtalk.com/document/orgapp/custom-bot-send-message-type

        :param str text: 待发送文本
        :param str,optional title: 标题，在通知和被引用时显示的简短信息。默认从文本中生成。
        :param List[str],optional at_mobiles: 需要 @ 的用户手机号。默认值为 None
        :param List[str],optional at_user_ids: 需要 @ 的用户 UserID。默认值为 None
        :param bool,optional at_all: 是否 @ 所有人。默认值为 False

        :raise DingTalkWebhookException:
        """
        text = text if isinstance(text, str) else "\n\n".join(text)
        title = title or self._gen_title(text)
        at = {"isAtAll": at_all}
        if at_user_ids:
            at["atUserIds"] = at_user_ids
        if at_mobiles:
            at["atMobiles"] = at_mobiles
        response = httpx.post(url=self.webhook_url(),json={"msgtype": "markdown", "markdown": {"title": title, "text": text}, "at": at})
        self.__handle_response(response)

    def send_action_card(self, text: List[str]|str, title:str|None = None, btn_orientation:Literal["0","1"] = "0",
                         single_jump:Tuple[str,str]|None = None, btns_jump:List[Tuple[str,str]]|None = None):
        """
        发送跳转 ActionCard 消息。

        **注意：**
        同时传 `single_jump` 和 `btns_jump`，仅 `single_jump` 生效。

        :param str text: 待发送文本，支持 Markdown 部分语法。
        :param str,optional title: 标题，在通知和被引用时显示的简短信息。默认从文本中生成。
        :param str,optional btn_orientation: 按钮排列方式，0-按钮竖直排列，1-按钮横向排列。默认值为 "0"
        :param Tuple[str,str],optional single_jump: 传此参数为单个按钮，元组内第一项为按钮的标题，第二项为按钮链接。
        :param Tuple[str,str],optional btns_jump: 传此参数为多个按钮，元组内第一项为按钮的标题，第二项为按钮链接。

        :raise DingTalkWebhookException:
        """
        text = text if isinstance(text, str) else "\n\n".join(text)
        title = title or self._gen_title(text)
        action_card = {"title": title, "text": text, "btnOrientation": str(btn_orientation)}

        if single_jump:
            action_card["singleTitle"], action_card["singleURL"] = single_jump
        if btns_jump:
            action_card["btns"] = [{"title": action_title, "actionURL": action_url} for action_title, action_url in btns_jump]

        response = httpx.post(url=self.webhook_url(), json={"msgtype": "actionCard", "actionCard": action_card})
        self.__handle_response(response)

    def send_feed_card(self, *args:Tuple[str,str,str]):
        """
        发送 FeedCard 消息。

        :param Tuple[str,str,str],optional args: 可以传入任意个具有三个元素的元组，分别为 `(标题, 跳转链接, 缩略图链接)`

        :raise DingTalkWebhookException:
        """
        for a in args:
            print(a)
        links_data = [
            {"title": title, "messageURL": message_url, "picURL": pic_url}
            for title, message_url, pic_url in args
        ]
        response = httpx.post(url=self.webhook_url(), json={"msgtype": "feedCard", "feedCard": {"links": links_data}})
        self.__handle_response(response)


class DingTalkAppResource(ConfigurableResource):
    """
[钉钉服务端 API](https://open.dingtalk.com/document/orgapp/api-overview) 企业内部应用部分的第三方封装。

通过此资源，可以调用部分钉钉服务端 API。具体封装的 API 可以在 IDE 中通过引入 `DingTalkAppClient` 类来查看 IDE 提示：

```python
from dagster_dingtalk import DingTalkAppClient

dingtalk: DingTalkAppClient
```

### 配置项:

- **AppID** (str):
    应用应用唯一标识 AppID，作为缓存标识符使用。不传入则不缓存鉴权。
- **AgentID** (int, optional):
    原企业内部应用 AgentId ，部分 API 会使用到。默认值为 None
- **AppName** (str, optional):
    应用名。
- **ClientId** (str):
    应用的 Client ID ，原 AppKey 和 SuiteKey
- **ClientSecret** (str):
    应用的 Client Secret ，原 AppSecret 和 SuiteSecret

### 用例

##### 1. 使用单一的企业内部应用资源。

```python
from dagster_dingtalk import DingTalkAppResource, DingTalkAppClient
from dagster import op, In, OpExecutionContext, job, Definitions, EnvVar

@op(required_resource_keys={"dingtalk"}, ins={"user_id": In(str)})
def op_user_info(context:OpExecutionContext, user_id:str):
    dingtalk:DingTalkAppClient = context.resources.dingtalk
    result = dingtalk.通讯录管理.用户管理.查询用户详情(user_id).get('result')
    context.log.info(result)

@job
def job_user_info():
    op_user_info()

defs = Definitions(
    jobs=[job_user_info],
    resources={"dingtalk": DingTalkAppResource(
        AppID = "<the-app-id>",
        ClientId = "<the-client-id>",
        ClientSecret = EnvVar("<the-client-secret-env-name>"),
    )})
```

##### 2. 启动时动态构建企业内部应用资源, 可参考 [Dagster文档 | 在启动时配置资源](https://docs.dagster.io/concepts/resources#configuring-resources-at-launch-time)

```python
from dagster_dingtalk import DingTalkAppResource, DingTalkAppClient
from dagster import op, In, OpExecutionContext, job, Definitions, schedule, RunRequest, RunConfig, EnvVar

@op(required_resource_keys={"dingtalk"}, ins={"user_id": In(str)})
def op_user_info(context:OpExecutionContext, user_id:str):
    dingtalk:DingTalkAppClient = context.resources.dingtalk
    result = dingtalk.通讯录管理.用户管理.查询用户详情(user_id).get('result')
    context.log.info(result)

@job
def job_user_info():
    op_user_info()

dingtalk_apps = {
    "App1" : DingTalkAppResource(
        AppID = "<app-1-app-id>",
        ClientId = "<app-1-client-id>",
        ClientSecret = EnvVar("<app-1-client-secret-env-name>"),
    ),
    "App2" : DingTalkAppResource(
        AppID = "<app-2-app-id>",
        ClientId = "<app-2-client-id>",
        ClientSecret = EnvVar("<app-2-client-secret-env-name>"),
    )
}

defs = Definitions(jobs=[job_user_info], resources={"dingtalk": DingTalkAppResource.configure_at_launch()})

@schedule(cron_schedule="20 9 * * *", job=job_user_info)
def schedule_user_info():
    return RunRequest(run_config=RunConfig(
        ops={"op_user_info": {"inputs": {"user_id": "<the-user-id>"}}},
        resources={"dingtalk": dingtalk_apps["App1"]},
    ))
```

### 注意:

应该永远避免直接将密钥字符串直接配置给资源，这会导致在 dagster 前端用户界面暴露密钥。你可以在代码中注册临时的环境变量，或从系统中引入环境变量。
    """

    AppID: str = Field(description="应用应用唯一标识 AppID，作为缓存标识符使用。不传入则不缓存鉴权。")
    AgentID: Optional[int] = Field(default=None, description="原企业内部应用AgentId ，部分API会使用到。")
    AppName: Optional[str] = Field(default=None, description="应用名。")
    ClientId: str = Field(description="应用的 Client ID (原 AppKey 和 SuiteKey)")
    ClientSecret: str = Field(description="应用的 Client Secret (原 AppSecret 和 SuiteSecret)")

    @classmethod
    def _is_dagster_maintained(cls) -> bool:
        return False

    def create_resource(self, context: InitResourceContext) -> DingTalkClient:
        """
        返回一个 `DingTalkClient` 实例。
        :param context:
        :return:
        """
        return DingTalkClient(
            app_id=self.AppID,
            agent_id=self.AgentID,
            app_name=self.AppName,
            client_id=self.ClientId,
            client_secret=self.ClientSecret
        )
