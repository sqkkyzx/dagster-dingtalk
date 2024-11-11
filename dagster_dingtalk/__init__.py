# noinspection PyProtectedMember
from dagster._core.libraries import DagsterLibraryRegistry

from dagster_dingtalk.resources import DingTalkResource, MultiDingTalkResource
from dagster_dingtalk.resources import DingTalkWebhookResource, MultiDingTalkWebhookResource
# from dagster_dingtalk.operations import DingTalkWebhookOp
from dagster_dingtalk.version import __version__

DagsterLibraryRegistry.register("dagster-dingtalk", __version__)
