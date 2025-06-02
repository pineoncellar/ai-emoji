from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi import Body
from pydantic import BaseModel
from src.emoji_manager.manager import emoji_manager
from .utils import generate_filename
from src.common.utils_image import image_path_to_base64
import os

router = APIRouter()

class MatchRequest(BaseModel):
    text: str

@router.post("/upload")
async def upload_image(image: UploadFile = File(...)):
    """图片上报接口"""
    try:
        filename = generate_filename(image)
        image_data = await image.read()
        filepath = await emoji_manager.save_unreviewed_image(image_data, filename)
        return {
            "status": "success",
            "message": "图片已保存待审核",
            "filename": filename,
            "preview_url": f"/preview/unreviewed/{filename}"
        }
    except Exception as e:
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
            "status": "success",
            "text": request.text,
            "emoji_path": file_path,
            "description": description,
            "base64": base64_data
        }
    raise HTTPException(status_code=404, detail="未找到匹配的表情包")

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
