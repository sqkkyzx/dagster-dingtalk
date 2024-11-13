# 钉钉与 Dagster 集成

---

## 介绍

该 Dagster 集成是为了更便捷的调用钉钉（DingTalk）的API，集成提供了两个 Dagster Resource。


## DingTalkWebhookResource

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

##### 2. 启动时动态构建 Webhook 资源, 可参考 [Dagster文档 | 在启动时配置资源](https://docs.dagster.io/concepts/resources#configuring-resources-at-launch-time)

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


## DingTalkAppResource

该 Dagster 资源允许定义一个钉钉的 API Client，更加便捷地调用钉钉服务端企业内部应用 API。

该资源是 [钉钉服务端 API](https://open.dingtalk.com/document/orgapp/api-overview) 企业内部应用部分常用 HTTP API 的第三方封装，
未采用官方 SDK 。具体封装的 API 可以在 IDE 中通过引入 `DingTalkAppClient` 类来查看 IDE 提示：

```python
from dagster_dingtalk import DingTalkAppClient

dingtalk: DingTalkAppClient
```


**特别注意：`DingTalkAppClient` 采用了 ASCII 字符来命名实例方法。** 

> 这是为了与
> [钉钉服务端 API 文档](https://open.dingtalk.com/document/orgapp/api-overview) 里的中文 API 
> 保持完全一致命名，以便于更符合直觉地进行调用和快速查阅文档。因此，可以按 
> [钉钉服务端 API 文档](https://open.dingtalk.com/document/orgapp/api-overview) 
> 中的层级，通过链式调用来发起 API 请求。例如：
> 
> `dingtalk.智能人事.花名册.获取花名册元数据()`


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


## 提醒:

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

