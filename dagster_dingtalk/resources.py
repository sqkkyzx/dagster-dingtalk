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


class DingTalkWebhookResource(ConfigurableResource):
    """
    定义一个钉钉群 Webhook 机器人资源，可以用来发送各类通知。

    钉钉API文档：
    https://open.dingtalk.com/document/orgapp/custom-bot-send-message-type

    Args:
        access_token (str): 机器人 Webhook 地址中的 access_token 值。
        secret (str, optional): 如使用加签安全配置，则需传签名密钥。默认值为 None。
        alias (str, optional): 如提供别名，可以在使用 `MultiDingTalkWebhookResource` 中使用别名进行 webhook 选择。默认值为 None。
        base_url (str, optional): 通用地址，一般无需更改。默认值为 “https://oapi.dingtalk.com/robot/send”。

    """
    access_token: str = Field(description="Webhook地址中的 access_token 部分")
    secret: Optional[str] = Field(default=None, description="如使用加签安全配置，需传签名密钥")
    alias: Optional[str] = Field(default=None, description="如提供别名，将来可以使用别名进行选择")
    base_url: str = Field(default="https://oapi.dingtalk.com/robot/send", description="Webhook的通用地址，无需更改")

    def webhook_url(self):
        """
        实时生成加签或未加签的 Webhook URL。

        钉钉API文档：
        https://open.dingtalk.com/document/robots/custom-robot-access

        Returns:
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

        Args:
            text: 原文

        Returns:
            str: 标题
        """
        return re.sub(r'[\n#>* ]', '', text[:12])

    def send_text(self, text: str,
                  at_mobiles:List[str]|None = None, at_user_ids:List[str]|None = None, at_all:bool = False):
        """
        发送文本消息。

        钉钉API文档：
        https://open.dingtalk.com/document/orgapp/custom-bot-send-message-type

        Args:
            text (str): 待发送文本
            at_mobiles (List[str], optional): 需要 @ 的用户手机号。默认值为 None
            at_user_ids (List[str], optional): 需要 @ 的用户 UserID。默认值为 None
            at_all (bool, optional): 是否 @ 所有人。默认值为 False
        """
        at = {"isAtAll": at_all}
        if at_user_ids:
            at["atUserIds"] = at_user_ids
        if at_mobiles:
            at["atMobiles"] = at_mobiles
        httpx.post(url=self.webhook_url(), json={"msgtype": "text", "text": {"content": text}, "at": at})

    def send_link(self, text: str, message_url:str, title:str|None = None, pic_url:str = ""):
        """
        发送 Link 消息。

        钉钉API文档：
        https://open.dingtalk.com/document/orgapp/custom-bot-send-message-type

        Args:
            text (str): 待发送文本
            message_url (str): 链接的 Url
            title (str, optional): 标题，在通知和被引用时显示的简短信息。默认从文本中生成。
            pic_url (str, optional): 图片的 Url，默认为 None
        """
        title = title or self._gen_title(text)
        httpx.post(
            url=self.webhook_url(),
            json={"msgtype": "link", "link": {"title": title, "text": text, "picUrl": pic_url, "messageUrl": message_url}}
        )

    def send_markdown(self, text: List[str]|str, title:str|None = None,
                      at_mobiles:List[str]|None = None, at_user_ids:List[str]|None = None, at_all:bool = False):
        """
        发送 Markdown 消息。支持的语法有：
            # 一级标题
            ## 二级标题
            ### 三级标题
            #### 四级标题
            ##### 五级标题
            ###### 六级标题
            > 引用
            **加粗**
            *斜体*
            [链接跳转](https://example.com/doc.html)
            ![图片预览](https://example.com/pic.jpg)
            - 无序列表
            1. 有序列表

        钉钉API文档：
        https://open.dingtalk.com/document/orgapp/custom-bot-send-message-type

        Args:
            text (str): 待发送文本
            title (str, optional): 标题，在通知和被引用时显示的简短信息。默认从文本中生成。
            at_mobiles (List[str], optional): 需要 @ 的用户手机号。默认值为 None
            at_user_ids (List[str], optional): 需要 @ 的用户 UserID。默认值为 None
            at_all (bool, optional): 是否 @ 所有人。默认值为 False
        """
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
        """
        发送跳转 ActionCard 消息。

        Args:
            text (str): 待发送文本，支持 Markdown 部分语法。
            title (str, optional): 标题，在通知和被引用时显示的简短信息。默认从文本中生成。
            btn_orientation (str, optional):  按钮排列方式，0-按钮竖直排列，1-按钮横向排列。默认值为 "0"
            single_jump(Tuple[str,str], optional): 传此参数为单个按钮，元组内第一项为按钮的标题，第二项为按钮链接。
            btns_jump(Tuple[str,str], optional): 传此参数为多个按钮，元组内第一项为按钮的标题，第二项为按钮链接。

        Notes:
            同时传 single_jump 和 btns_jump，仅 single_jump 生效。

        """
        text = text if isinstance(text, str) else "\n\n".join(text)
        title = title or self._gen_title(text)
        action_card = {"title": title, "text": text, "btnOrientation": str(btn_orientation)}
        if single_jump:
            action_card["singleTitle"], action_card["singleURL"] = single_jump
            httpx.post(url=self.webhook_url(), json={"msgtype": "actionCard", "actionCard": action_card})
        elif btns_jump:
            action_card["btns"] = [{"title": action_title, "actionURL": action_url} for action_title, action_url in btns_jump]
            httpx.post(url=self.webhook_url(), json={"msgtype": "actionCard", "actionCard": action_card})
        else:
            pass

    def send_feed_card(self, *args:Tuple[str,str,str]):
        """
        发送 FeedCard 消息。

        Args:
            args (Tuple[str,str,str]): 可以传入任意个具有三个元素的元组，分别为 (标题, 跳转链接, 缩略图链接)

        """
        for a in args:
            print(a)
        links_data = [
            {"title": title, "messageURL": message_url, "picURL": pic_url}
            for title, message_url, pic_url in args
        ]
        httpx.post(url=self.webhook_url(), json={"msgtype": "feedCard", "feedCard": {"links": links_data}})


class DingTalkAppResource(ConfigurableResource):
    """
    [钉钉服务端 API](https://open.dingtalk.com/document/orgapp/api-overview) 企业内部应用部分的第三方封装。
    通过此资源，可以调用部分钉钉服务端API。

    Notes:
        不包含全部的API端点。

    Args:
        AppID (str): 应用应用唯一标识 AppID，作为缓存标识符使用。不传入则不缓存鉴权。
        AgentID (int, optional): 原企业内部应用 AgentId ，部分 API 会使用到。默认值为 None
        AppName (str, optional): 应用名。
        ClientId (str): 应用的 Client ID ，原 AppKey 和 SuiteKey
        ClientSecret (str): 应用的 Client Secret ，原 AppSecret 和 SuiteSecret
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
        return DingTalkClient(
            app_id=self.AppID,
            agent_id=self.AgentID,
            app_name=self.AppName,
            client_id=self.ClientId,
            client_secret=self.ClientSecret
        )
