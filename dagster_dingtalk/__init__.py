# noinspection PyProtectedMember
from dagster._core.libraries import DagsterLibraryRegistry

from dagster_dingtalk.resources import DingTalkAppResource
from dagster_dingtalk.resources import DingTalkWebhookResource
from dagster_dingtalk.app_client import DingTalkClient as DingTalkAppClient
# from dagster_dingtalk.operations import DingTalkWebhookOp
from dagster_dingtalk.version import __version__

DagsterLibraryRegistry.register("dagster-dingtalk", __version__)
