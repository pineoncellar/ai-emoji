"""
图像请求处理模块 - 简化版
专注于图像识别分析功能，提供简单便捷的API调用方式
"""
import base64
import hashlib
import io
import json
import os
import re
import time
import traceback
from typing import Dict, Any, Tuple, Union, List, Optional
import aiohttp
import asyncio

from datetime import datetime
from PIL import Image

from src.common.logger_manager import get_logger
from src.common.config import global_config

logger = get_logger("img_request")


class RequestError(Exception):
    """请求错误的基类"""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return self.message


class PayLoadTooLargeError(Exception):
    """请求体过大错误"""
    def __init__(self):
        super().__init__("请求体过大")
        self.message = "请求体过大，请尝试压缩图片或减少输入内容"

    def __str__(self):
        return self.message


class ImageRequest:
    """图像请求处理类，专注于图像识别分析功能"""
    
    # 定义需要特殊处理的模型列表
    MODELS_NEEDING_TRANSFORMATION = [
        "o1", "o1-mini", "o1-preview", "o1-pro", "o3", "o3-mini", "o4-mini",
        "o1-2024-12-17", "o1-mini-2024-09-12", "o1-preview-2024-09-12", 
        "o1-pro-2025-03-19", "o3-2025-04-16", "o3-mini-2025-01-31o4-mini",
        "o4-mini-2025-04-16"
    ]
    
    def __init__(self, model: str, **kwargs):
        """
        初始化图像请求处理对象
        
        Args:
            model: 模型名称字符串
            **kwargs: 其它参数，如temperature、max_tokens等
        """
        self.model_name = model
        self.api_key = kwargs.get("api_key", global_config.model.api_key)
        self.base_url = kwargs.get("base_url", global_config.model.base_url)
        
        # 模型参数
        self.temperature = kwargs.get("temperature", 0.7)
        self.max_tokens = kwargs.get("max_tokens", global_config.model.max_token)
        self.stream = kwargs.get("stream", False)
        self.enable_thinking = kwargs.get("enable_thinking", False)
        
        # 记录请求类型
        self.request_type = kwargs.get("request_type", "default")
        
        logger.debug(f"初始化图像请求处理对象: {model}")

    async def analyze_image(self, prompt: str, image_base64: str, image_format: str) -> Tuple[str, str]:
        """
        分析图像并返回结果
        
        Args:
            prompt: 提示词
            image_base64: 图片base64编码
            image_format: 图片格式(jpg, png等)
            
        Returns:
            Tuple[str, str]: (分析结果, 思考过程)
        """
        try:
            # 处理图像大小
            if len(image_base64) > 1.5 * 1024 * 1024:  # 如果大于1.5MB
                image_base64 = compress_image(image_base64, target_size=0.8 * 1024 * 1024)
                
            response = await self._execute_request(
                endpoint="/chat/completions",
                prompt=prompt,
                image_base64=image_base64,
                image_format=image_format
            )
            
            content, reasoning = response
            logger.info(f"图像分析完成，结果长度: {len(content)}")
            return content, reasoning
            
        except PayLoadTooLargeError:
            logger.warning("图像过大，尝试压缩后重新请求")
            # 压缩图像后重试
            image_base64 = compress_image(image_base64, target_size=0.5 * 1024 * 1024)
            response = await self._execute_request(
                endpoint="/chat/completions",
                prompt=prompt,
                image_base64=image_base64,
                image_format=image_format
            )
            content, reasoning = response
            return content, reasoning
            
        except Exception as e:
            logger.error(f"图像分析失败: {str(e)}")
            logger.error(traceback.format_exc())
            raise    
    
    async def _execute_request(self, endpoint: str, prompt: str, image_base64: str = None, 
                              image_format: str = None, payload: dict = None) -> Tuple[str, str]:
        """
        执行API请求
        
        Args:
            endpoint: API端点
            prompt: 提示词
            image_base64: 图片base64编码
            image_format: 图片格式
            payload: 自定义请求体
            
        Returns:
            Tuple[str, str]: (响应内容, 思考过程)
        """
        # 准备请求
        max_retries = 3
        base_wait = 5
        
        api_url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        # 构建请求体
        if payload is None:
            payload = await self._build_payload(prompt, image_base64, image_format)
        
        headers = await self._build_headers()
        
        # 执行请求，带重试
        for retry in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    logger.debug(f"发送请求到 {api_url}，retry={retry}")
                    async with session.post(api_url, headers=headers, json=payload, timeout=120) as response:
                        if response.status >= 400 and response.status < 500:
                            if response.status == 413:
                                raise PayLoadTooLargeError()
                                
                            # 其他客户端错误，直接终止
                            error_text = await response.text()
                            error_msg = f"请求被拒绝(状态码:{response.status}): {error_text}"
                            logger.error(error_msg)
                            raise RequestError(error_msg)
                            
                        if response.status >= 500 or response.status == 429:
                            # 服务器错误或频率限制，可以重试
                            wait_time = base_wait * (2 ** retry)
                            logger.warning(f"请求失败(状态码:{response.status})，{wait_time}秒后重试")
                            await asyncio.sleep(wait_time)
                            continue
                        
                        # 成功响应
                        response.raise_for_status()
                        result = await response.json()
                        
                        # 处理响应
                        return self._parse_response(result)
            
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                wait_time = base_wait * (2 ** retry)
                logger.warning(f"网络错误: {str(e)}，{wait_time}秒后重试")
                await asyncio.sleep(wait_time)
                continue
                
            except PayLoadTooLargeError:
                # 特殊处理请求体过大的错误
                raise
                
            except Exception as e:
                if retry < max_retries - 1:
                    wait_time = base_wait * (2 ** retry)
                    logger.warning(f"请求错误: {str(e)}，{wait_time}秒后重试")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"请求失败: {str(e)}")
                    logger.error(traceback.format_exc())
                    raise
        
        # 达到最大重试次数
        logger.error(f"达到最大重试次数({max_retries})，请求失败")
        raise RequestError("请求失败，请稍后重试")

    async def _build_payload(self, prompt: str, image_base64: str = None, image_format: str = None) -> dict:
        """构建请求体"""
        # 准备基本参数
        params = {
            "model": self.model_name,
            "temperature": self.temperature,
        }
        
        # 对特定模型进行参数转换
        if self.model_name.lower() in self.MODELS_NEEDING_TRANSFORMATION:
            if "max_tokens" in params:
                params["max_completion_tokens"] = params.pop("max_tokens")
            else:
                params["max_completion_tokens"] = self.max_tokens
        else:
            params["max_tokens"] = self.max_tokens
            
        # 添加思考功能的参数
        if self.enable_thinking:
            params["enable_thinking"] = True
            
        # 添加流式输出参数
        if self.stream:
            params["stream"] = True
            
        # 构建消息
        if image_base64:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/{image_format.lower()};base64,{image_base64}"},
                        },
                    ],
                }
            ]
        else:
            messages = [{"role": "user", "content": prompt}]
            
        # 组合最终请求体
        payload = {
            "model": self.model_name,
            "messages": messages,
            **params
        }
        
        return payload

    async def _build_headers(self) -> dict:
        """构建请求头"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _parse_response(self, result: dict) -> Tuple[str, str]:
        """
        解析响应结果
        
        Args:
            result: API响应的JSON数据
            
        Returns:
            Tuple[str, str]: (响应内容, 思考过程)
        """
        if "choices" not in result or not result["choices"]:
            logger.warning("响应中没有choices字段")
            return "API响应异常，请重试", ""
            
        message = result["choices"][0].get("message", {})
        content = message.get("content", "")
        
        # 提取思考过程
        reasoning_content = message.get("model_extra", {}).get("reasoning_content", "")
        
        # 如果没有单独的思考字段，尝试从内容中提取
        if not reasoning_content:
            content, reasoning_content = self._extract_reasoning(content)
            
        # 记录使用情况
        usage = result.get("usage", {})
        if usage:
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)
            
            logger.info(
                f"Token使用情况 - 模型: {self.model_name}, 类型: {self.request_type}, "
                f"提示词: {prompt_tokens}, 完成: {completion_tokens}, 总计: {total_tokens}"
            )
            
        return content, reasoning_content

    @staticmethod
    def _extract_reasoning(content: str) -> Tuple[str, str]:
        """从内容中提取思考过程"""
        match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
        if match:
            reasoning = match.group(1).strip()
            # 移除思考部分
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            return content, reasoning
        else:
            return content, ""


def compress_image(base64_data: str, target_size: int = 0.8 * 1024 * 1024) -> str:
    """
    压缩base64格式的图片到指定大小
    
    Args:
        base64_data: base64编码的图片数据
        target_size: 目标文件大小（字节），默认0.8MB
        
    Returns:
        str: 压缩后的base64图片数据
    """
    try:
        # 将base64转换为字节数据
        image_data = base64.b64decode(base64_data)
        
        # 如果已经小于目标大小，直接返回原图
        if len(image_data) <= target_size:
            return base64_data
            
        # 将字节数据转换为图片对象
        img = Image.open(io.BytesIO(image_data))
        
        # 获取原始尺寸
        original_width, original_height = img.size
        
        # 计算缩放比例
        scale = min(1.0, (target_size / len(image_data)) ** 0.5)
        
        # 计算新的尺寸
        new_width = int(original_width * scale)
        new_height = int(original_height * scale)
        
        # 创建内存缓冲区
        output_buffer = io.BytesIO()
        
        # 处理图像
        if getattr(img, "is_animated", False):
            # 对于GIF等动态图像，保留原样但降低质量
            img.save(output_buffer, format=img.format, optimize=True, quality=70)
        else:
            # 对于静态图像，调整大小
            resized_img = img.resize((new_width, new_height), Image.LANCZOS)
            resized_img.save(output_buffer, format=img.format, optimize=True, quality=85)
            
        # 获取压缩后的数据并转换为base64
        compressed_data = output_buffer.getvalue()
        logger.info(f"压缩图片: {original_width}x{original_height} -> {new_width}x{new_height}")
        logger.info(f"压缩前大小: {len(image_data) / 1024:.1f}KB, 压缩后大小: {len(compressed_data) / 1024:.1f}KB")
        
        return base64.b64encode(compressed_data).decode("utf-8")
        
    except Exception as e:
        logger.error(f"压缩图片失败: {str(e)}")
        logger.error(traceback.format_exc())
        return base64_data


async def analyze_emotion_from_image(image_path: str, prompt: str = None) -> Tuple[str, List[str]]:
    """
    从图像中分析情感
    
    Args:
        image_path: 图像文件路径
        prompt: 自定义提示词，如果为None则使用默认提示词
        
    Returns:
        Tuple[str, List[str]]: (描述, 情感标签列表)
    """
    try:
        # 读取图像文件
        with open(image_path, 'rb') as img_file:
            image_bytes = img_file.read()
            
        # 转换为base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # 获取图像格式
        image_format = os.path.splitext(image_path)[1][1:].lower()
        if not image_format:
            image_format = "jpg"  # 默认格式
            
        # 实例化请求对象
        img_request = ImageRequest(
            model=global_config.model.vlm,
            temperature=0.3,
            max_tokens=1000,
            request_type="emotion"
        )
        
        # 使用默认提示词或自定义提示词
        if not prompt:
            if image_format.lower() == "gif":
                prompt = "这是一个动态图表情包，描述一下表情包表达的情感和内容，从互联网梗和表情符号的角度分析。"
            else:
                prompt = "这是一个表情包，请详细描述一下表情包所表达的情感和内容，从互联网梗和表情符号的角度分析。"
        
        # 分析图像
        description, _ = await img_request.analyze_image(prompt, image_base64, image_format)
        
        # 提取情感标签
        emotion_prompt = f"""
        请识别这个表情包的含义和适用场景，给我简短的描述，每个描述不要超过15个字
        这是表情包的描述：'{description}'
        你可以关注其幽默和讽刺意味，从互联网梗的角度去分析
        请直接输出描述，不要出现任何其他内容，如果有多个描述，用逗号分隔
        """
        
        # 使用普通模型提取情感标签
        emotion_request = ImageRequest(
            model=global_config.model.utils,
            temperature=0.7,
            max_tokens=600,
            request_type="emotion_extract"
        )
        
        emotions_text, _ = await emotion_request.analyze_image(emotion_prompt, "", "")
        emotions = [e.strip() for e in emotions_text.split(",") if e.strip()]
        
        # 限制情感标签数量
        if len(emotions) > 5:
            emotions = emotions[:5]
            
        return description, emotions
        
    except Exception as e:
        logger.error(f"分析图像情感失败: {str(e)}")
        logger.error(traceback.format_exc())
        return "无法分析图像", []


# 简单的测试函数
async def test_img_request():
    """测试图像请求功能"""
    try:
        # 从文件加载图像
        test_image_path = "data/emoji_unreviewed/e710f9ee18469c3eec3e544ae207ad88.jpg"
        description, emotions = await analyze_emotion_from_image(test_image_path)
        
        print(f"图像描述: {description}")
        print(f"情感标签: {emotions}")
        return True
    except Exception as e:
        logger.error(f"测试失败: {str(e)}")
        logger.error(traceback.format_exc())
        return False
