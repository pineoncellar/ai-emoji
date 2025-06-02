import os
import hashlib
from fastapi import UploadFile

def generate_filename(file: UploadFile) -> str:
    """
    生成唯一的文件名，基于文件内容哈希。
    """
    content = file.file.read()
    file.file.seek(0)  # 重置文件指针
    file_hash = hashlib.md5(content).hexdigest()
    ext = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
    return f"{file_hash}{ext}"


def get_image_metadata(filename: str) -> dict:
    """
    获取图片的审核元数据。
    """
    meta_path = os.path.join("data", "emoji_approved", f"{filename}.meta")
    if not os.path.exists(meta_path):
        return None
    metadata = {}
    with open(meta_path, "r") as f:
        for line in f.readlines():
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    return metadata
