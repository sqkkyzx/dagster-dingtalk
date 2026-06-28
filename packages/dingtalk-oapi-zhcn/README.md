# dingtalk-oapi-zhcn

中文命名的钉钉开放平台服务端 OpenAPI 客户端。

```bash
pip install dingtalk-oapi-zhcn
```

```python
from dingtalk_oapi_zhcn import DingTalkClient

dingtalk = DingTalkClient(
    app_id="<app-id>",
    client_id="<client-id>",
    client_secret="<client-secret>",
    agent_id="<agent-id>",
)

result = dingtalk.通讯录管理.用户管理.查询用户详情("<user-id>")
```
