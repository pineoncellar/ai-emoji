from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi import Body, Request
from pydantic import BaseModel
from src.emoji_manager.manager import emoji_manager
from .utils import generate_filename
from src.common.utils_image import image_path_to_base64
from src.common.logger_manager import get_logger
import os
from typing import Optional
import aiohttp
import time
import ssl

logger = get_logger("routes")

router = APIRouter()

class MatchRequest(BaseModel):
    text: str

@router.post("/upload")
async def upload_image(
    request: Request
) -> dict:
    """
    图片上报接口，仅支持 JSON 格式的图片链接上传。

    Args:
        request (Request): 请求对象，需包含 image_url 字段

    Returns:
        dict: 上传结果
    """
    try:
        data = await request.json()
        url = data.get("image_url")
        if not url:
            raise HTTPException(status_code=400, detail="请提供图片链接")
        # 从链接下载图片
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        # 创建一个兼容性更好的 SSL 上下文
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers("DEFAULT@SECLEVEL=1")  # 降低安全级别以兼容老旧服务器
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, ssl=ssl_context) as resp:
                if resp.status != 200:
                    detail = f"图片链接{url}下载失败，状态码: {resp.status}"
                    try:
                        error_text = await resp.text()
                        detail += f"，响应内容: {error_text[:200]}"
                    except Exception:
                        pass
                    raise HTTPException(status_code=400, detail=detail)
                image_data = await resp.read()
        # 从链接推断文件名
        # filename = os.path.basename(url.split("?")[0])
        filename = f"{int(time.time() * 1000)}.jpg"
        filepath = await emoji_manager.save_unreviewed_image(image_data, filename)
        return {
            "status": "ok",
            "message": "图片已保存待审核"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传图片失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# @router.post("/approve/{filename}")
# async def approve_image(filename: str, user: str = "admin"):
#     """审核通过接口"""
#     success = await emoji_manager.approve_image(filename, user)
#     if success:
#         return {
#             "status": "success",
#             "message": "图片已批准",
#             "filename": filename,
#             "preview_url": f"/preview/approved/{filename}"
#         }
#     raise HTTPException(status_code=404, detail="图片不存在或审核失败")
# 
# @router.post("/register/{filename}")
# async def register_image(filename: str):
#     """注册已审核图片接口"""
#     success = await emoji_manager.register_approved_image(filename)
#     if success:
#         return {
#             "status": "success",
#             "message": "图片已成功注册为表情包",
#             "filename": filename
#         }
#     raise HTTPException(status_code=400, detail="图片注册失败")

# @router.post("/register-all")
# async def register_all_approved():
#     """批量注册所有已审核图片"""
#     results = await emoji_manager.batch_register_approved()
#     return {
#         "status": "success",
#         "message": "批量注册完成",
#         "results": results
#     }

@router.post("/match")
async def match_emoji_by_emotion(request: MatchRequest = Body(...)):
    """
    文本先用utils模型提取情感，再根据情感匹配表情包（POST方式，JSON格式）
    Args:
        request (MatchRequest): 包含待匹配文本的请求体
    Returns:
        dict: 匹配结果，包含表情包路径、描述和base64
    """
    result = await emoji_manager.get_emoji_by_utils_emotion(request.text)
    if result:
        file_path, description = result
        try:
            base64_data = image_path_to_base64(file_path)
        except Exception as e:
            base64_data = None
        return {
            "status": "ok",
            "text": request.text,
            "emoji_path": file_path,
            "description": description,
            "base64": base64_data
        }
    return {
        "status": "fail",
        "detail": "未找到匹配的表情包"
    }

# @router.get("/unreviewed-list")
# async def list_unreviewed_images():
#     """获取未审核图片列表"""
#     files = os.listdir(emoji_manager.UNREVIEWED_DIR)
#     images = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif"))]
#     return {
#         "count": len(images),
#         "images": [
#             {
#                 "filename": img,
#                 "preview_url": f"/preview/unreviewed/{img}",
#                 "upload_time": os.path.getctime(os.path.join(emoji_manager.UNREVIEWED_DIR, img))
#             } for img in images
#         ]
#     }

# @router.get("/approved-list")
# async def list_approved_images():
#     """获取已审核但未注册图片列表"""
#     files = os.listdir(emoji_manager.APPROVED_DIR)
#     images = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif"))]
#     result = []
#     for img in images:
#         metadata = get_image_metadata(img) or {}
#         result.append({
#             "filename": img,
#             "preview_url": f"/preview/approved/{img}",
#             "approved_by": metadata.get("approved_by", "unknown"),
#             "approve_time": metadata.get("approve_time", "unknown")
#         })
#     return {
#         "count": len(images),
#         "images": result
#     }
