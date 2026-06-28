from datetime import datetime

from dagster import OpExecutionContext

from dingtalk_oapi_zhcn.app_client import DingTalkClient


def upload_file_to_dingtalk(
        context:OpExecutionContext,
        parent_dentry_uuid:str,
        file_name:str,
        file_bytes:bytes,
        union_id:str,
        convert_to_online_doc:bool=True,
        conflict_strategy:str="OVERWRITE"
) -> dict:
    """
    上传文件到钉钉。必须封装到一个 op 中使用，并传入 op 的 context。
    :param context:
    :param parent_dentry_uuid:
    :param file_name:
    :param file_bytes:
    :param union_id:
    :param conflict_strategy:
    :param convert_to_online_doc:
    :return:
    """
    dingtalk:DingTalkClient = context.resources.dingtalk
    upload_info = dingtalk.文档文件.文件传输.获取文件上传信息(parentDentryUuid=parent_dentry_uuid, union_id=union_id)
    context.log.info(upload_info)

    upload_key = upload_info["uploadKey"]
    upload_url = upload_info["headerSignatureInfo"]["resourceUrls"][0]
    upload_headers = upload_info["headerSignatureInfo"]["headers"]

    dentry:dict = dingtalk.文档文件.文件传输.提交文件(
        parentDentryUuid=parent_dentry_uuid,
        union_id=union_id,
        upload_key=upload_key,
        url=upload_url,
        headers=upload_headers,
        file_content=file_bytes,
        file_name=file_name,
        convert_to_online_doc=convert_to_online_doc,
        conflictStrategy=conflict_strategy
    ).get("dentry")

    space_id=dentry.get("spaceId")
    dentry_id=dentry.get("id")

    res:dict = dingtalk.文档文件.存储管理.文件管理.重命名文件或文件夹(
        space_id, dentry_id, union_id, file_name
    )
    if res.get("code"):
        context.log.info(res)
        file_name = file_name.split(".")[0] + datetime.now().strftime("-%Y%m%d%H%M%S") + "." + file_name.split(".")[-1]
        res: dict = dingtalk.文档文件.存储管理.文件管理.重命名文件或文件夹(
            space_id, dentry_id, union_id, file_name
        )
        context.log.info(res)

    dentry = res.get("dentry")

    context.log.info(dentry)

    return dentry
