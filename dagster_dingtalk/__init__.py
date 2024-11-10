# noinspection PyProtectedMember
from dagster._core.libraries import DagsterLibraryRegistry

from dagster_dingtalk.resources import DingTalkAPIResource, DingTalkWebhookResource
from dagster_dingtalk.dynamic_ops import DingTalkWebhookOp
from dagster_dingtalk.version import __version__

DagsterLibraryRegistry.register("dagster-dingtalk", __version__)
