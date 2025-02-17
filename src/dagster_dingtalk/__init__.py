# noinspection PyProtectedMember
from dagster._core.libraries import DagsterLibraryRegistry
from dagster_dingtalk.version import __version__

from dagster_dingtalk.resources import DingTalkAppResource, DingTalkWebhookResource
from dagster_dingtalk.app_client import DingTalkClient as DingTalkAppClient
import dagster_dingtalk.operations  as dingtalk_op

DagsterLibraryRegistry.register("dagster-dingtalk", __version__)
