from dagster import In, OpExecutionContext, op, Out
from .app_client import DingTalkClient
from .resources import DingTalkWebhookResource


@op(description="钉钉Webhook发送文本消息",
    required_resource_keys={'dingtalk_webhook'},
    ins={
        "text": In(str),
        "at": In(default_value=None, description="@列表，传List[str]解析为userId,传List[int]解析为phone，传ALL解析为全部。")
    })
def op_send_text(context: OpExecutionContext, text, at):
    webhook:DingTalkWebhookResource = context.resources.dingtalk_webhook
    if isinstance(at, str) and at == 'ALL':
        webhook.send_text(text=text, at_all=True)
    if isinstance(at, list) and isinstance(at[0], str):
        webhook.send_text(text=text, at_user_ids=at)
    if isinstance(at, list) and isinstance(at[0], int):
        at = [str(mobile) for mobile in at]
        webhook.send_text(text=text, at_mobiles=at)
    if not at:
        webhook.send_text(text=text)


@op(description="钉钉Webhook发送Markdown消息",
    required_resource_keys={'dingtalk_webhook'},
    ins={
        "text": In(str, description="Markdown 内容"),
        "title": In(str, default_value='', description="标题"),
        "at": In(default_value=None, description="传 List[str] @userIds ，传 List[int] @mobiles ，传 \"ALL\" @所有人。")
    })
def op_send_markdown(context: OpExecutionContext, text, title, at):
    webhook:DingTalkWebhookResource = context.resources.dingtalk_webhook
    if isinstance(at, str) and at == 'ALL':
        webhook.send_markdown(text=text, title=title, at_all=True)
    if isinstance(at, list) and isinstance(at[0], str):
        webhook.send_markdown(text=text, title=title, at_user_ids=at)
    if isinstance(at, list) and isinstance(at[0], int):
        at = [str(mobile) for mobile in at]
        webhook.send_markdown(text=text, title=title, at_mobiles=at)
    if not at:
        webhook.send_markdown(text=text, title=title)


@op(description="更新钉钉互动卡片",
    required_resource_keys={"dingtalk"},
    ins={"card_param_map":In(), "out_track_id":In(str), "update_by_key":In(bool, default_value=True)},
    out={"is_success":Out(bool, is_required=False)})
def renew_card(context:OpExecutionContext, card_param_map, out_track_id, update_by_key):
    try:
        dingtalk_yunxiao: DingTalkClient = context.resources.dingtalk_yunxiao
        res = dingtalk_yunxiao.互动卡片.更新卡片(out_track_id=out_track_id, card_param_map=card_param_map, update_card_data_by_key=update_by_key)
        context.log.info(res)
        if res.get('success') and res.get('result'):
            return True
        else:
            return False
    except Exception as e:
        context.log.error(e)
        return False


@op(description="创建并发送钉钉互动卡片",
    ins={"search_type_name":In(str), "alert_content":In(str), "card_template_id":In(str), "card_param_map":In(), "out_track_id":In(str), "open_space_id":In(str)},
    out={"is_success":Out(bool, is_required=False)}, required_resource_keys={"dingtalk"})
def send_revenue_dt_card(context:OpExecutionContext, search_type_name, alert_content,card_template_id, card_param_map, out_track_id, open_space_id):
    try:
        dingtalk_yunxiao: DingTalkClient = context.resources.dingtalk_yunxiao
        res = dingtalk_yunxiao.互动卡片.创建并投放卡片(
            search_type_name=search_type_name,
            search_desc=alert_content,
            card_template_id=card_template_id,
            card_param_map=card_param_map,
            alert_content=alert_content,
            out_track_id=out_track_id,
            open_space_ids=[open_space_id]
        )
        context.log.info(res)
        return res.get("success")
    except Exception as e:
        context.log.error(e)
        return False
