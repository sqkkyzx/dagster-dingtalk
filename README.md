# 钉钉与 Dagster 集成

---

## 介绍

该 Dagster 集成是为了更便捷的调用钉钉（DingTalk）的API，集成提供了两个 Dagster
Resource 和若干 Dagster Op 的封装。

### DingTalkWebhookResource

该 Dagster 资源允许定义一个钉钉自定义机器人的 Webhook 端点，发送文本、Markdown
、Link、 ActionCard、FeedCard 消息，消息具体样式可参考 
[钉钉开放平台 | 自定义机器人发送消息的消息类型](https://open.dingtalk.com/document/orgapp/custom-bot-send-message-type) 。


### DingTalkResource

该 Dagster 资源允许定义一个钉钉的 API Client，更加便捷地调用钉钉服务端 API (
仅企业内部应用)
