# noinspection PyProtectedMember
# from dagster._core.libraries import DagsterLibraryRegistry
# from dagster_dingtalk.version import __version__

from .resources import DingTalkAppResource, DingTalkWebhookResource
from .app_client import DingTalkClient as DingTalkAppClient
import operations  as dingtalk_op

# DagsterLibraryRegistry.register("dagster-dingtalk", __version__)
