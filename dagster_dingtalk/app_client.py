import logging
import pickle
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Literal
import platform

import httpx
from httpx import Client
from pydantic import BaseModel, Field


# noinspection NonAsciiCharacters
class DingTalkClient:
    def __init__(self, app_id: str, client_id: str, client_secret: str, app_name: str|None = None, agent_id: int|None = None):
        self.app_id: str = app_id
        self.app_name: str|None = app_name
        self.agent_id: int|None = agent_id
        self.client_id: str = client_id
        self.__client_secret: str = client_secret
        self.robot_code: str = client_id

        access_token: str = self.__get_access_token()
        self.api: Client = Client(base_url="https://api.dingtalk.com/", headers={"x-acs-dingtalk-access-token": access_token})
        self.oapi: Client = Client(base_url="https://oapi.dingtalk.com/", params={"access_token": access_token})

        self.智能人事 = 智能人事_API(self)
        self.通讯录管理 = 通讯录管理_API(self)
        self.文档文件 = 文档文件_API(self)
        self.互动卡片 = 互动卡片_API(self)
        self.OA审批 = OA审批_API(self)
        self.即时通信 = 即时通信_API(self)

    def __get_access_token(self) -> str:
        access_token_cache = Path.home() / ".dingtalk_cache"
        all_access_token: dict = {}
        access_token: str|None = None
        expire_in: int = 0
        renew_reason = None

        # 从缓存中读取
        if not access_token_cache.exists():
            renew_reason = f"鉴权缓存不存在"
        else:
            try:
                with open(access_token_cache, 'rb') as f:
                    all_access_token = pickle.loads(f.read())
            except Exception as e:
                logging.error(e)
                renew_reason = "鉴权缓存读取或解析错误"

        if all_access_token:
            app_access_token = all_access_token.get(self.app_id)
            access_token = app_access_token.get('access_token')
            expire_in = app_access_token.get('expire_in')
        else:
            renew_reason = f"鉴权缓存不存在该应用 {self.app_name}<{self.app_id}>"

        if not access_token:
            renew_reason = F"应用 {self.app_name}<{self.app_id}> 的鉴权缓存无效"
        if expire_in < int(time.time()):
            renew_reason = F"应用 {self.app_name}<{self.app_id}> 的鉴权缓存过期"

        if renew_reason is None:
            return access_token
        else:
            logging.warning(renew_reason)
            response = Client().post(
                url="https://api.dingtalk.com/v1.0/oauth2/accessToken",
                json={"appKey": self.client_id, "appSecret": self.__client_secret},
            )
            access_token:str = response.json().get("accessToken")
            expire_in:int = response.json().get("expireIn") + int(time.time()) - 60
            with open(access_token_cache, 'wb') as f:
                all_access_token[self.app_id] = {
                    "access_token": access_token,
                    "expire_in": expire_in,
                }
                f.write(pickle.dumps(all_access_token))
            return access_token

# noinspection NonAsciiCharacters
class 智能人事_API:
    def __init__(self, _client:DingTalkClient):
        self.__client:DingTalkClient = _client
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
        self.__client:DingTalkClient = _client
        self.用户管理 = 通讯录管理_用户管理_API(_client)
        self.部门管理 = 通讯录管理_部门管理_API(_client)

    def 查询用户详情(self, user_id:str, language:str = "zh_CN"):
        return self.用户管理.查询用户详情(user_id, language)

# noinspection NonAsciiCharacters
class 通讯录管理_用户管理_API:
    def __init__(self, _client:DingTalkClient):
        self.__client:DingTalkClient = _client

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
class 通讯录管理_部门管理_API:
    def __init__(self, _client:DingTalkClient):
        self.__client:DingTalkClient = _client

    def 获取部门详情(self, dept_id: int, language:str = "zh_CN") -> dict:
        """
        调用本接口，根据部门ID获取指定部门详情。

        https://open.dingtalk.com/document/orgapp/query-department-details0-v2

        :param dept_id: 部门 ID ，根部门 ID 为 1。
        :param language: 通讯录语言。zh_CN en_US
        """
        response = self.__client.oapi.post(
            url="/topapi/v2/department/get",
            json={"language": language, "dept_id": dept_id}
        )
        return response.json()

    def 获取部门列表(self, dept_id: int, language:str = "zh_CN"):
        """
        调用本接口，获取下一级部门基础信息。

        https://open.dingtalk.com/document/orgapp/obtain-the-department-list-v2

        :param dept_id: 部门 ID ，根部门 ID 为 1。
        :param language: 通讯录语言。zh_CN en_US
        """
        response = self.__client.oapi.post(
            url="/topapi/v2/department/listsub",
            json={"language": language, "dept_id": dept_id}
        )
        return response.json()

# noinspection NonAsciiCharacters
class 文档文件_API:
    def __init__(self, _client:DingTalkClient):
        self.__client:DingTalkClient = _client
        self.媒体文件 = 文档文件_媒体文件_API(_client)
        self.文件传输 = 文档文件_文件传输_API(_client)

# noinspection NonAsciiCharacters
class 文档文件_媒体文件_API:
    def __init__(self, _client:DingTalkClient):
        self.__client:DingTalkClient = _client

    def 上传媒体文件(self, file_path:Path|str, media_type:Literal['image', 'voice', 'video', 'file']) -> dict:
        """
        调用本接口，上传图片、语音媒体资源文件以及普通文件，接口返回媒体资源标识 media_id。

        https://open.dingtalk.com/document/orgapp/upload-media-files

        :param file_path: 本地文件路径
        :param media_type: 媒体类型，支持 'image', 'voice', 'video', 'file'

        :return:
            {
                "errcode": 0,
                "errmsg": "ok",
                "media_id": "$iAEKAqDBgTNAk",
                "created_at": 1605863153573,
                "type": "image"
            }
        """
        with open(file_path, 'rb') as f:
            response = self.__client.oapi.post(url=f"/media/upload?type={media_type}", files={'media': f})
        return response.json()

# noinspection NonAsciiCharacters
class 文档文件_文件传输_API:
    def __init__(self, _client:DingTalkClient):
        self.__client:DingTalkClient = _client

    def 获取文件上传信息(self, space_id:int, union_id:str, multi_part:bool = False) -> dict:
        """
        调用本接口，上传图片、语音媒体资源文件以及普通文件，接口返回媒体资源标识 media_id。

        https://open.dingtalk.com/document/orgapp/upload-media-files

        :param space_id: 空间Id。
        :param union_id: 操作者unionId。
        :param multi_part: 是否需要分片上传。默认值为 False

        :return:
            {
                "uploadKey": str,
                "storageDriver": str,
                "protocol": str,
                "headerSignatureInfo": {
                    "resourceUrls" : ["resourceUrl"],
                    "headers" : {
                      "key" : "header_value"
                    },
                }
            }
        """
        response = self.__client.api.post(
            url=f"/v1.0/storage/spaces/{space_id}/files/uploadInfos/query",
            params={'unionId': union_id},
            json={
                "protocol": "HEADER_SIGNATURE",
                "multipart": multi_part
            }
        )
        return response.json()

    def 提交文件(self, url:str, headers:dict, file_path:Path|str, space_id:int, union_id:str,
                 upload_key:str, convert_to_online_doc:bool = False) -> dict:
        """
        调用本接口，上传图片、语音媒体资源文件以及普通文件，接口返回媒体资源标识 media_id。

        https://open.dingtalk.com/document/orgapp/upload-media-files

        :param url: 获取文件上传信息得到的 resourceUrl。
        :param headers: 获取文件上传信息得到的 headers。
        :param file_path: 文件路径
        :param space_id: 空间Id。
        :param union_id: 操作者unionId。
        :param upload_key: 添加文件唯一标识。
        :param convert_to_online_doc: 是否转换成在线文档。默认值 False

        :return:
            {
                "uploadKey": str,
                "storageDriver": str,
                "protocol": str,
                "headerSignatureInfo": dict,
            }
        """
        with open(file_path, 'rb') as f:
            httpx.put(
                url=url,
                files={"file":f},
                headers=headers
            )

        response = self.__client.api.post(
            url = f"/v2.0/storage/spaces/files/{space_id}/commit?unionId={union_id}",
            json = {
                "uploadKey": upload_key,
                "name": file_path.split("/")[-1],
                "convertToOnlineDoc": convert_to_online_doc
            }
        )
        return response.json()

# noinspection NonAsciiCharacters
class 互动卡片_API:
    def __init__(self, _client:DingTalkClient):
        self.__client:DingTalkClient = _client

    def 创建并投放卡片(
            self, search_type_name: str, search_desc: str, card_template_id: str, card_param_map: dict,
            alert_content: str, open_space_ids: List[str], out_track_id: str, support_forward: bool = True,
            call_back_type: str = "STREAM", expired_time_millis:int = 0
    ) -> dict:
        """
        创建并投放卡片。当前仅支持 IM群聊, IM机器人单聊, 吊顶 三种场域类型。

        https://open.dingtalk.com/document/orgapp/create-and-deliver-cards

        :param card_template_id: 卡片模板 ID
        :param open_space_ids: 卡片投放场域 Id
        :param out_track_id: 卡片唯一标识
        :param card_param_map: 卡片数据
        :param search_type_name: 卡片类型名
        :param search_desc: 卡片消息展示
        :param alert_content: 通知内容
        :param call_back_type: 回调模式
        :param support_forward: 是否支持转发
        :param expired_time_millis: 吊顶投放过期时间。当投放内容为吊顶时必须传参。
        """

        open_space_id = f"dtv1.card//{';'.join(open_space_ids)}"

        payload = {
            "cardTemplateId": card_template_id,
            "outTrackId": out_track_id,
            "openSpaceId": open_space_id,
            "callbackType": call_back_type,
            "cardData": {"cardParamMap": card_param_map}
        }

        open_space_model = {
                "supportForward": support_forward,
                "searchSupport": {"searchTypeName": search_type_name, "searchDesc": search_desc},
                "notification": {"alertContent": alert_content, "notificationOff": False}
            }

        if 'IM_GROUP' in open_space_id.upper():
            payload["imGroupOpenSpaceModel"] = open_space_model
            payload["imGroupOpenDeliverModel"] = {"robotCode": self.__client.robot_code}

        if 'IM_ROBOT' in open_space_id.upper():
            payload["imRobotOpenSpaceModel"] = open_space_model
            payload["imRobotOpenDeliverModel"] = {"spaceType": "IM_ROBOT", "robotCode": self.__client.robot_code}

        if 'ONE_BOX' in open_space_id.upper():
            if expired_time_millis == 0:
                expired_time_millis = int(time.time()+3600)*1000
            payload["topOpenSpaceModel"] = {"spaceType": "ONE_BOX"}
            payload["topOpenDeliverModel"] = {"platforms": ["android","ios","win","mac"], "expiredTimeMillis": expired_time_millis,}

        response = self.__client.api.post(
            url="/v1.0/card/instances/createAndDeliver",
            json=payload
        )

        return response.json()

    def 更新卡片(self, out_track_id: str, card_param_map: dict, update_card_data_by_key:bool=True) -> dict:
        """
        调用本接口，实现主动更新卡片数据。

        https://open.dingtalk.com/document/orgapp/interactive-card-update-interface

        :param out_track_id: 外部卡片实例Id。
        :param card_param_map: 卡片模板内容。
        :param update_card_data_by_key: True-按 key 更新 cardData 数据 False-覆盖更新 cardData 数据
        :return:
            {success: bool, result: bool}
        """

        response = self.__client.api.put(
            url="/v1.0/card/instances",
            json={
                "outTrackId": out_track_id,
                "cardData": {"cardParamMap": card_param_map},
                "cardUpdateOptions": {"updateCardDataByKey": update_card_data_by_key}
            }
        )

        return response.json()

# noinspection NonAsciiCharacters
class OA审批_API:
    def __init__(self, _client:DingTalkClient):
        self.__client:DingTalkClient = _client
        self.审批实例 = OA审批_审批实例_API(_client)
        self.审批钉盘 = OA审批_审批钉盘_API(_client)

# noinspection NonAsciiCharacters
class OA审批_审批实例_API:
    def __init__(self, _client:DingTalkClient):
        self.__client:DingTalkClient = _client

    class CommentAttachment(BaseModel):
        spaceId: str = Field(description="钉盘空间ID")
        fileSize: str = Field(description="文件大小")
        fileId: str = Field(description="文件ID")
        fileName: str = Field(description="文件名称")
        fileType: str = Field(description="文件类型")

    def 获取单个审批实例详情(self, instance_id:str) -> dict:
        """
        调用本接口可以获取审批实例详情数据，根据审批实例ID，获取审批实例详情，包括审批实例标题、发起人的userId、审批人userId、操作记录列表等内容。

        https://open.dingtalk.com/document/orgapp/obtains-the-details-of-a-single-approval-instance-pop

        :param instance_id: 审批实例ID。

        :return:
            {
                "success": boolean,
                "result": {}
            }
        """
        response = self.__client.api.get(url="/v1.0/workflow/processInstances", params={'processInstanceId': instance_id})
        return response.json()

    def 撤销审批实例(self, instance_id:str, is_system:bool = True, remark:str|None = None, operating_user_id:str = None) -> dict:
        """
        撤销发起的处于流程中的审批实例。审批发起15秒内不能撤销审批流程。本接口只能撤销流程中的审批实例，不能撤销已审批完成的审批实例。

        https://open.dingtalk.com/document/orgapp/revoke-an-approval-instance

        :param instance_id: 审批实例ID。
        :param is_system: 是否通过系统操作。默认为 True。当为 false 时，需要传发起人才能撤销。
        :param remark: 终止说明。
        :param operating_user_id: 操作人的userId。is_system 为 false 时必填。

        :return:
            {
                "success": boolean,
                "result": {}
            }
        """
        response = self.__client.api.post(
            url="/v1.0/workflow/processInstances",
            json={
              "processInstanceId" : instance_id,
              "isSystem" : is_system,
              "remark" : remark,
              "operatingUserId" : operating_user_id
            }
        )
        return response.json()

    def 添加审批评论(
            self, instance_id:str, text:str, comment_user_id: str,
            photos: List[str]|None = None, attachments: List[CommentAttachment]|None = None
    ) -> dict:
        """
        调用本接口可以获取审批实例详情数据，根据审批实例ID，获取审批实例详情，包括审批实例标题、发起人的userId、审批人userId、操作记录列表等内容。

        其中，添加审批评论附件需调用获取审批钉盘空间信息接口，获取钉盘空间的上传权限，并获取审批钉盘空间spaceId。

        https://open.dingtalk.com/document/orgapp/obtains-the-details-of-a-single-approval-instance-pop

        :param instance_id: 审批实例 ID。
        :param text: 评论的内容。
        :param comment_user_id: 评论人的 UserId
        :param photos: 图片的 URL 链接的列表，默认为 None。
        :param attachments: 附件列表，默认为 None。添加审批评论附件需将文件上传至审批钉盘空间，可以获取到相关接口参数。

        :return:
            {
                "success": boolean,
                "result": boolean
            }
        """

        data = {
            'processInstanceId': instance_id,
            'text': text,
            'commentUserId': comment_user_id,
        }

        if photos or attachments:
            data.update({'file': {"photos": photos, "attachments": attachments}})

        response = self.__client.api.post(
            url="/v1.0/workflow/processInstances/comments",
            json=data
        )
        return response.json()

    def 获取审批实例ID列表(
            self, process_code:str, start_time:datetime, end_time:datetime, next_token: int = 0, max_results: int = 20,
            statuses: Literal["RUNNING", "TERMINATED", "COMPLETED"]|None = None, user_ids = List[str]
    ) -> dict:
        """
        获取权限范围内的相关部门审批实例ID列表。

        https://open.dingtalk.com/document/orgapp/obtain-an-approval-list-of-instance-ids

        :param user_ids:
        :param process_code: 审批流模板的 code。
        :param start_time: 审批实例开始时间。
        :param end_time: 审批实例结束时间。
        :param next_token: 分页游标, 首次调用传 0, 默认值为 0
        :param max_results: 分页小，最多传20，默认值为 20
        :param statuses: 筛选流程实例状态，默认为 None，表示不筛选。 RUNNING-审批中 TERMINATED-已撤销 COMPLETED-审批完成

        :return:
            {
                "success": boolean,
                "result": {}
            }
        """
        response = self.__client.api.post(
            url="/v1.0/workflow/processes/instanceIds/query",
            json={
              "processCode" : process_code,
              "startTime" : int(start_time.timestamp()*1000),
              "endTime" : int(end_time.timestamp()*1000),
              "nextToken" : next_token,
              "maxResults" : max_results,
              "userIds" : user_ids,
              "statuses" : statuses
            })
        return response.json()

# noinspection NonAsciiCharacters
class OA审批_审批钉盘_API:
    def __init__(self, _client:DingTalkClient):
        self.__client:DingTalkClient = _client

    def 获取审批钉盘空间信息(self, user_id:str) -> dict:
        """
        获取审批钉盘空间的ID并授予当前用户上传附件的权限。

        https://open.dingtalk.com/document/orgapp/obtains-the-information-about-approval-nail-disk

        :param user_id: 用户的userId。

        :return:
            {
                "success": bool,
                "result": {
                    "spaceId": int
                }
            }
        """
        response = self.__client.api.post(
            url="/v1.0/workflow/processInstances/spaces/infos/query",
            json={
              "userId" : user_id,
              "agentId" : self.__client.agent_id
            })
        return response.json()

# noinspection NonAsciiCharacters
class 即时通信_API:
    def __init__(self, _client:DingTalkClient):
        self.__client:DingTalkClient = _client
        self.工作通知 = 即时通信_工作通知_API(_client)

# noinspection NonAsciiCharacters
class 即时通信_工作通知_API:
    def __init__(self, _client:DingTalkClient):
        self.__client:DingTalkClient = _client

    def 发送工作通知(self, msg:dict, to_all_user:bool=True, user_list:List[str]|None=None, dept_id_list:List[str]|None=None) -> dict:
        """
        工作通知消息是以某个应用的名义推送到员工的工作通知消息，例如生日祝福、入职提醒等。可以发送文本、语音、链接等。

        注意：
        1. 企业内部应用发送消息单次最多只能给5000人发送。
        2. 企业内部应用每天给每个员工最多可发送500条消息通知。
        3. 该接口是异步发送消息，接口返回成功并不表示用户一定会收到消息，需要通过获取工作通知消息的发送结果接口查询是否给用户发送成功。

        :param msg:  消息数据格式参考 https://open.dingtalk.com/document/orgapp/message-types-and-data-format?spm=ding_open_doc.document.0.0.74742580198aRf
        :param to_all_user: 是否发送给企业全部用户。如果为否，则必须传入 user_list 或 dept_id_list
        :param user_list: 接收者的 userid 列表，最大用户列表长度 100。
        :param dept_id_list: 接收者的部门 id 列表，最大列表长度 20 。接收者是部门 ID 时，包括子部门下的所有用户。
        :return:
        """
        response = self.__client.oapi.post(
            url="/topapi/message/corpconversation/asyncsend_v2",
            json={
                "agent_id" : self.__client.agent_id,
                "to_all_user": to_all_user,
                "userid_list" : ','.join(user_list) if user_list else None,
                "dept_id_list" : ','.join(dept_id_list) if dept_id_list else None,
                "msg": msg
            })
        return response.json()
