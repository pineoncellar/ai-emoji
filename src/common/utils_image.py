import base64
import os
import io
from typing import Optional
from PIL import Image
import numpy as np

from src.common.logger_manager import get_logger

logger = get_logger("chat_image")


class ImageManager:
    _instance = None
    IMAGE_DIR = "data"  # 图像存储根目录

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._initialized = True

    @staticmethod
    def transform_gif(gif_base64: str, similarity_threshold: float = 1000.0, max_frames: int = 15) -> Optional[str]:
        """将GIF转换为水平拼接的静态图像, 跳过相似的帧

        Args:
            gif_base64: GIF的base64编码字符串
            similarity_threshold: 判定帧相似的阈值 (MSE)，越小表示要求差异越大才算不同帧，默认1000.0
            max_frames: 最大抽取的帧数，默认15

        Returns:
            Optional[str]: 拼接后的JPG图像的base64编码字符串, 或者在失败时返回None
        """
        try:
            gif_data = base64.b64decode(gif_base64)
            gif = Image.open(io.BytesIO(gif_data))
            all_frames = []
            try:
                while True:
                    gif.seek(len(all_frames))
                    frame = gif.convert("RGB")
                    all_frames.append(frame.copy())
            except EOFError:
                pass
            if not all_frames:
                logger.warning("GIF中没有找到任何帧")
                return None
            selected_frames = []
            last_selected_frame_np = None
            for i, current_frame in enumerate(all_frames):
                current_frame_np = np.array(current_frame)
                if i == 0:
                    selected_frames.append(current_frame)
                    last_selected_frame_np = current_frame_np
                    continue
                if last_selected_frame_np is not None:
                    mse = np.mean((current_frame_np - last_selected_frame_np) ** 2)
                    if mse > similarity_threshold:
                        selected_frames.append(current_frame)
                        last_selected_frame_np = current_frame_np
                        if len(selected_frames) >= max_frames:
                            break
            if not selected_frames:
                logger.warning("处理后没有选中任何帧")
                return None
            frame_width, frame_height = selected_frames[0].size
            target_height = 200
            if frame_height == 0:
                logger.error("帧高度为0，无法计算缩放尺寸")
                return None
            target_width = int((target_height / frame_height) * frame_width)
            if target_width == 0:
                logger.warning(f"计算出的目标宽度为0 (原始尺寸 {frame_width}x{frame_height})，调整为1")
                target_width = 1
            resized_frames = [
                frame.resize((target_width, target_height), Image.Resampling.LANCZOS) for frame in selected_frames
            ]
            total_width = target_width * len(resized_frames)
            if total_width == 0 and len(resized_frames) > 0:
                logger.warning("计算出的总宽度为0，但有选中帧，可能目标宽度太小")
                total_width = len(resized_frames)
            elif total_width == 0:
                logger.error("计算出的总宽度为0且无选中帧")
                return None
            combined_image = Image.new("RGB", (total_width, target_height))
            for idx, frame in enumerate(resized_frames):
                combined_image.paste(frame, (idx * target_width, 0))
            buffer = io.BytesIO()
            combined_image.save(buffer, format="JPEG", quality=85)
            result_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return result_base64
        except MemoryError:
            logger.error("GIF转换失败: 内存不足，可能是GIF太大或帧数太多")
            return None
        except Exception as e:
            logger.error(f"GIF转换失败: {str(e)}", exc_info=True)
            return None


# 创建全局单例
image_manager = ImageManager()


def image_path_to_base64(image_path: str) -> str:
    """将图片路径转换为base64编码
    Args:
        image_path: 图片文件路径
    Returns:
        str: base64编码的图片数据
    Raises:
        FileNotFoundError: 当图片文件不存在时
        IOError: 当读取图片文件失败时
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    with open(image_path, "rb") as f:
        image_data = f.read()
        if not image_data:
            raise IOError(f"读取图片文件失败: {image_path}")
        return base64.b64encode(image_data).decode("utf-8")
