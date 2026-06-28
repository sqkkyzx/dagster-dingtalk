# noinspection PyProtectedMember
from dagster._core.libraries import DagsterLibraryRegistry
from dingtalk_oapi_zhcn.app_client import DingTalkClient as DingTalkAppClient
from dagster_dingtalk.version import __version__

from dagster_dingtalk.resources import DingTalkAppResource, DingTalkWebhookResource
import dagster_dingtalk.operations  as dingtalk_op

DagsterLibraryRegistry.register("dagster-dingtalk", __version__)
