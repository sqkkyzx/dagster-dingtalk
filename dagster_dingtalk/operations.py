from dagster import In, OpExecutionContext, op

# noinspection PyProtectedMember
from dagster._annotations import experimental


@experimental
@op(description="使用钉钉 Webhook 发送文本消息",
    required_resource_keys={'dingtalk_webhook'},
    ins={"text": In(str)})
def op_send_simple_text(context: OpExecutionContext, text):
    webhook = context.resources.dingtalk_webhook
    webhook.send_text(text)

@op(description="使用钉钉 Webhook 发送 Markdown 消息",
    required_resource_keys={'dingtalk_webhook'},
    ins={"text": In(str), "title": In(str, default_value='')})
def op_simple_markdown(context: OpExecutionContext, text, title):
    webhook = context.resources.dingtalk_webhook
    webhook.send_text(text, title)
