#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
表情包管理器模块 - 管理表情包的上传、审核、注册和匹配服务
"""

import os
import asyncio
import base64
import hashlib
import time
from typing import Optional, Tuple, List, Dict, Any

from src.common.config import global_config
from src.common.logger_manager import get_logger
from src.emoji_manager.emoji_manager import (
    EmojiManager as EmojiManagerBase,
    BASE_DIR,
    _ensure_emoji_dir,
    _load_emoji_json,
    _save_emoji_json,
    MaiEmoji
)
from src.common.img_request import ImageRequest

logger = get_logger("emoji")

# 定义各种存储目录
UNREVIEWED_DIR = os.path.join(BASE_DIR, "emoji_unreviewed")  # 未审核的表情包存储目录
APPROVED_DIR = os.path.join(BASE_DIR, "emoji_approved")  # 已审核但未注册的表情包存储目录


class EmojiManager(EmojiManagerBase):
    """表情包管理器，扩展基础表情包管理器功能"""
    
    def __init__(self) -> None:
        """初始化表情包管理器"""
        super().__init__()
        self.UNREVIEWED_DIR = UNREVIEWED_DIR
        self.APPROVED_DIR = APPROVED_DIR
        
    async def initialize(self) -> None:
        """异步初始化表情包管理器"""
        # 确保目录存在
        _ensure_emoji_dir()
        os.makedirs(UNREVIEWED_DIR, exist_ok=True)
        os.makedirs(APPROVED_DIR, exist_ok=True)
        
        # 调用父类的初始化方法
        super().initialize()
        
        logger.info("表情包管理器初始化完成")
        
    async def save_unreviewed_image(self, image_data: bytes, filename: str) -> str:
        """
        保存上传的未审核图片
        
        Args:
            image_data: 图片二进制数据
            filename: 文件名
            
        Returns:
            str: 保存后的文件路径
        """
        # 确保目录存在
        os.makedirs(UNREVIEWED_DIR, exist_ok=True)
        
        # 保存文件
        file_path = os.path.join(UNREVIEWED_DIR, filename)
        
        # 使用asyncio创建异步任务来写入文件
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._write_file(file_path, image_data))
            
        logger.info(f"[上传] 保存未审核图片: {filename}")
        return file_path
    
    def _write_file(self, file_path: str, data: bytes) -> None:
        """
        写入文件的同步辅助方法
        
        Args:
            file_path: 文件路径
            data: 文件数据
        """
        with open(file_path, "wb") as f:
            f.write(data)
    
    async def approve_image(self, filename: str, user: str) -> bool:
        """
        审核通过表情包
        
        Args:
            filename: 文件名
            user: 审核者用户名
            
        Returns:
            bool: 审核是否成功
        """
        source_path = os.path.join(UNREVIEWED_DIR, filename)
        if not os.path.exists(source_path):
            logger.error(f"[审核失败] 未审核文件不存在: {filename}")
            return False
            
        # 确保目录存在
        os.makedirs(APPROVED_DIR, exist_ok=True)
        
        # 移动文件
        destination_path = os.path.join(APPROVED_DIR, filename)
        try:
            # 如果目标已存在，先删除
            if os.path.exists(destination_path):
                os.remove(destination_path)
                
            # 移动文件
            os.rename(source_path, destination_path)
            
            # 保存元数据
            await self._save_metadata(filename, {
                "approved_by": user,
                "approve_time": time.time(),
                "original_filename": filename
            })
            
            logger.info(f"[审核] 表情包已通过审核: {filename} (审核人: {user})")
            return True
        except Exception as e:
            logger.error(f"[审核失败] 移动或保存元数据失败: {str(e)}")
            return False
    
    async def register_approved_image(self, filename: str) -> bool:
        """
        注册已审核的表情包
        
        Args:
            filename: 文件名
            
        Returns:
            bool: 注册是否成功
        """
        file_path = os.path.join(APPROVED_DIR, filename)
        if not os.path.exists(file_path):
            logger.error(f"[注册失败] 已审核文件不存在: {filename}")
            return False
            
        try:
            # 复制文件到表情包目录
            target_path = os.path.join(BASE_DIR, "emoji", filename)
            with open(file_path, "rb") as src_file:
                content = src_file.read()
                with open(target_path, "wb") as dst_file:
                    dst_file.write(content)
            
            # 注册表情包
            registered = await self.register_emoji_by_filename(filename)
            if registered:
                # 注册成功后删除审核目录中的文件
                try:
                    os.remove(file_path)
                except Exception as e:
                    logger.warning(f"[警告] 删除已注册的审核文件失败: {str(e)}")
                return True
            else:
                logger.error(f"[注册失败] 表情包注册失败: {filename}")
                # 注册失败，删除复制的文件
                if os.path.exists(target_path):
                    os.remove(target_path)
                return False
        except Exception as e:
            logger.error(f"[注册失败] 处理表情包时发生错误: {str(e)}")
            return False
    
    async def batch_register_approved(self) -> Dict[str, bool]:
        """
        批量注册所有已审核的表情包
        
        Returns:
            Dict[str, bool]: 每个文件的注册结果
        """
        results = {}
        
        # 确保目录存在
        os.makedirs(APPROVED_DIR, exist_ok=True)
        
        # 获取所有已审核的表情包
        files = os.listdir(APPROVED_DIR)
        image_files = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif"))]
        
        for filename in image_files:
            results[filename] = await self.register_approved_image(filename)
        
        logger.info(f"[批量注册] 完成, 成功: {sum(results.values())}/{len(results)}")
        return results
    
    async def get_emoji_by_utils_emotion(self, text: str) -> Optional[Tuple[str, str]]:
        """
        先用utils模型提取文本情感，再用情感文本调用get_emoji_for_text获取表情包
        Args:
            text (str): 输入文本
        Returns:
            Optional[Tuple[str, str]]: (表情包路径, 描述) 或 None
        """
        try:
            logger.info(f"提取文本情感: {text}")
            # 用utils模型提取情感
            prompt = f"请根据以下文本，提取其表达的情感或适用场景，简短输出：\n{text}\n只输出情感，不要其他内容。多个用“,”分隔。"
            emotion_request = ImageRequest(
                model=global_config.model.utils,
                temperature=0.7,
                max_tokens=64,
                request_type="text_emotion_extract"
            )
            emotions_text, _ = await emotion_request.analyze_image(prompt, image_base64="", image_format="")
            logger.info(f"提取情感成功: {emotions_text}")
            # 取全部情感关键词，依次尝试匹配表情包，优先第一个匹配成功的
            emotions = [e.strip() for e in emotions_text.split(",") if e.strip()] if emotions_text else [text]
            for emotion in emotions:
                if not emotion:
                    continue
                result = await self.get_emoji_for_text(emotion)
                if result:
                    return result
            # 如果都没有匹配到，返回None
            return None
        except Exception as e:
            logger.error(f"[情感提取匹配] 失败: {str(e)}")
            return None



# 创建表情包管理器实例
emoji_manager = EmojiManager()