from dagster import In, OpExecutionContext, op
from pydantic import Field


class DingTalkWebhookOp:
    @op(description="使用钉钉 Webhook 发送文本消息",
        config_schema={"dingtalk_webhook_key": Field(str)},
        ins={"text": In(str)},
    )
    def send_simple_text(self, context: OpExecutionContext, text):
        webhook = getattr(context.resources, context.op_config["dingtalk_webhook_key"])
        webhook.send_text(text)

    @op(description="使用钉钉 Webhook 发送 Markdown 消息",
        config_schema={"dingtalk_webhook_key": Field(str)},
        ins={"text": In(str), "title": In(str, default_value='')},
    )
    def send_simple_markdown(self, context: OpExecutionContext, text, title):
        webhook = getattr(context.resources, context.op_config["dingtalk_webhook_key"])
        webhook.send_text(text, title)
