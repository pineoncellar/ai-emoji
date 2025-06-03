import asyncio
import hashlib
import os
import random
import time
import traceback
import json
from typing import Optional, Tuple, List, Any
from PIL import Image
import io
import re
import base64

from src.common.config import global_config
from src.common.utils_image import image_path_to_base64, image_manager
from src.common.logger_manager import get_logger
from src.common.img_request import analyze_emotion_from_image

logger = get_logger("emoji")

BASE_DIR = os.path.join("data")
EMOJI_APPROVED_DIR = os.path.join(BASE_DIR, "emoji_approved")  # 表情包存储目录
EMOJI_REGISTED_DIR = os.path.join(BASE_DIR, "emoji_registed")  # 已注册的表情包注册目录
EMOJI_JSON_PATH = os.path.join(BASE_DIR, "emoji_data.json")  # json数据存储路径
MAX_EMOJI_FOR_PROMPT = 20


def _ensure_emoji_dir() -> None:
    os.makedirs(EMOJI_APPROVED_DIR, exist_ok=True)
    os.makedirs(EMOJI_REGISTED_DIR, exist_ok=True)
    os.makedirs(BASE_DIR, exist_ok=True)
    if not os.path.exists(EMOJI_JSON_PATH):
        with open(EMOJI_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)


def _load_emoji_json() -> list:
    if not os.path.exists(EMOJI_JSON_PATH):
        return []
    with open(EMOJI_JSON_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []


def _save_emoji_json(data: list) -> None:
    with open(EMOJI_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class MaiEmoji:
    """定义一个表情包"""
    def __init__(self, full_path: str):
        if not full_path:
            raise ValueError("full_path cannot be empty")
        self.full_path = full_path
        self.path = os.path.dirname(full_path)
        self.filename = os.path.basename(full_path)
        self.embedding = []
        self.hash = ""
        self.description = ""
        self.emotion = []
        self.usage_count = 0
        self.last_used_time = time.time()
        self.register_time = time.time()
        self.is_deleted = False
        self.format = ""

    def to_dict(self) -> dict:
        return {
            "hash": self.hash,
            "full_path": self.full_path,
            "filename": self.filename,
            "description": self.description,
            "emotion": self.emotion,
            "usage_count": self.usage_count,
            "last_used_time": self.last_used_time,
            "register_time": self.register_time,
            "is_deleted": self.is_deleted,
            "format": self.format,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MaiEmoji":
        obj = cls(d["full_path"])
        obj.hash = d.get("hash", "")
        obj.description = d.get("description", "")
        obj.emotion = d.get("emotion", [])
        obj.usage_count = d.get("usage_count", 0)
        obj.last_used_time = d.get("last_used_time", time.time())
        obj.register_time = d.get("register_time", time.time())
        obj.is_deleted = d.get("is_deleted", False)
        obj.format = d.get("format", "")
        return obj

    async def initialize_hash_format(self) -> Optional[bool]:
        try:
            if not os.path.exists(self.full_path):
                logger.error(f"[初始化错误] 表情包文件不存在: {self.full_path}")
                self.is_deleted = True
                return None
            image_base64 = image_path_to_base64(self.full_path)
            if image_base64 is None:
                logger.error(f"[初始化错误] 无法读取或转换Base64: {self.full_path}")
                self.is_deleted = True
                return None
            image_bytes = base64.b64decode(image_base64)
            self.hash = hashlib.md5(image_bytes).hexdigest()
            try:
                with Image.open(io.BytesIO(image_bytes)) as img:
                    self.format = img.format.lower()
            except Exception as pil_error:
                logger.error(f"[初始化错误] Pillow无法处理图片 ({self.filename}): {pil_error}")
                logger.error(traceback.format_exc())
                self.is_deleted = True
                return None
            return True
        except Exception as e:
            logger.error(f"[初始化错误] 初始化表情包时发生未预期错误 ({self.filename}): {str(e)}")
            logger.error(traceback.format_exc())
            self.is_deleted = True
            return None

    async def register_to_json(self) -> bool:
        try:
            source_full_path = self.full_path
            destination_full_path = os.path.join(EMOJI_REGISTED_DIR, self.filename)
            if not os.path.exists(source_full_path):
                logger.error(f"[错误] 源文件不存在: {source_full_path}")
                return False
            try:
                if os.path.exists(destination_full_path):
                    os.remove(destination_full_path)
                os.rename(source_full_path, destination_full_path)
                self.full_path = destination_full_path
                self.path = EMOJI_REGISTED_DIR
            except Exception as move_error:
                logger.error(f"[错误] 移动文件失败: {str(move_error)}")
                return False
            # 写入json
            emoji_data = _load_emoji_json()
            emoji_data.append(self.to_dict())
            _save_emoji_json(emoji_data)
            logger.info(f"[注册] 表情包信息保存到json: {self.filename} ({self.emotion})")
            return True
        except Exception as e:
            logger.error(f"[错误] 注册表情包失败 ({self.filename}): {str(e)}")
            logger.error(traceback.format_exc())
            return False

    async def delete(self) -> bool:
        try:
            file_to_delete = self.full_path
            if os.path.exists(file_to_delete):
                try:
                    os.remove(file_to_delete)
                    logger.debug(f"[删除] 文件: {file_to_delete}")
                except Exception as e:
                    logger.error(f"[错误] 删除文件失败 {file_to_delete}: {str(e)}")
            emoji_data = _load_emoji_json()
            new_data = [d for d in emoji_data if d.get("hash") != self.hash]
            _save_emoji_json(new_data)
            self.is_deleted = True
            return True
        except Exception as e:
            logger.error(f"[错误] 删除表情包失败 ({self.filename}): {str(e)}")
            return False


def _emoji_objects_to_readable_list(emoji_objects: List["MaiEmoji"]) -> List[str]:
    emoji_info_list = []
    for i, emoji in enumerate(emoji_objects):
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(emoji.register_time))
        emoji_info = f"编号: {i + 1}\n描述: {emoji.description}\n使用次数: {emoji.usage_count}\n添加时间: {time_str}\n"
        emoji_info_list.append(emoji_info)
    return emoji_info_list


def _load_all_emoji_objects() -> List["MaiEmoji"]:
    emoji_data = _load_emoji_json()
    return [MaiEmoji.from_dict(d) for d in emoji_data if not d.get("is_deleted", False)]


def _save_all_emoji_objects(objs: List["MaiEmoji"]) -> None:
    _save_emoji_json([obj.to_dict() for obj in objs])


async def clear_temp_emoji() -> None:
    logger.info("[清理] 开始清理缓存...")
    for need_clear in (os.path.join(BASE_DIR, "emoji"), os.path.join(BASE_DIR, "image")):
        if os.path.exists(need_clear):
            files = os.listdir(need_clear)
            if len(files) > 100:
                for filename in files:
                    file_path = os.path.join(need_clear, filename)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        logger.debug(f"[清理] 删除: {filename}")
    logger.info("[清理] 完成")


async def clean_unused_emojis(emoji_dir: str, emoji_objects: List["MaiEmoji"]) -> None:
    if not os.path.exists(emoji_dir):
        logger.warning(f"[清理] 目标目录不存在，跳过清理: {emoji_dir}")
        return
    try:
        tracked_full_paths = {emoji.full_path for emoji in emoji_objects if not emoji.is_deleted}
        cleaned_count = 0
        for file_name in os.listdir(emoji_dir):
            file_full_path = os.path.join(emoji_dir, file_name)
            if not os.path.isfile(file_full_path):
                continue
            if file_full_path not in tracked_full_paths:
                try:
                    os.remove(file_full_path)
                    logger.info(f"[清理] 删除未追踪的表情包文件: {file_full_path}")
                    cleaned_count += 1
                except Exception as e:
                    logger.error(f"[错误] 删除文件时出错 ({file_full_path}): {str(e)}")
        if cleaned_count > 0:
            logger.info(f"[清理] 在目录 {emoji_dir} 中清理了 {cleaned_count} 个破损表情包。")
        else:
            logger.info(f"[清理] 目录 {emoji_dir} 中没有需要清理的。")
    except Exception as e:
        logger.error(f"[错误] 清理未使用表情包文件时出错 ({emoji_dir}): {str(e)}")


class EmojiManager:
    _instance = None
    def __new__(cls) -> "EmojiManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    def __init__(self) -> None:
        if self._initialized:
            return
        self._scan_task = None
        # self.vlm = LLMRequest(model=global_config.model.vlm, temperature=0.3, max_tokens=1000, request_type="emoji")
        # self.llm_emotion_judge = LLMRequest(
        #     model=global_config.model.utils, max_tokens=600, request_type="emoji"
        # )
        self.emoji_num = 0
        self.emoji_num_max = global_config.emoji.max_reg_num
        self.emoji_num_max_reach_deletion = global_config.emoji.do_replace
        self.emoji_objects: list[MaiEmoji] = []
        logger.info("启动表情包管理器")
    def initialize(self) -> None:
        _ensure_emoji_dir()
        self.emoji_objects = _load_all_emoji_objects()
        self.emoji_num = len(self.emoji_objects)
        self._initialized = True
    def _ensure_db(self) -> None:
        if not self._initialized:
            self.initialize()
        if not self._initialized:
            raise RuntimeError("EmojiManager not initialized")
    def record_usage(self, emoji_hash: str) -> None:
        try:
            for emoji in self.emoji_objects:
                if emoji.hash == emoji_hash:
                    emoji.usage_count += 1
                    emoji.last_used_time = time.time()
                    _save_all_emoji_objects(self.emoji_objects)
                    return
            logger.error(f"记录表情使用失败: 未找到 hash 为 {emoji_hash} 的表情包")
        except Exception as e:
            logger.error(f"记录表情使用失败: {str(e)}")
            
    async def get_emoji_for_text(self, text_emotion: str) -> Optional[Tuple[str, str]]:
        try:
            self._ensure_db()
            all_emojis = self.emoji_objects
            if not all_emojis:
                logger.warning("内存中没有任何表情包对象")
                return None
            emoji_similarities = []
            for emoji in all_emojis:
                if emoji.is_deleted:
                    continue
                emotions = emoji.emotion
                if not emotions:
                    continue
                similarity_limit = global_config.emoji.similarity_limit
                max_similarity = 0
                best_matching_emotion = ""
                for emotion in emotions:
                    distance = self._levenshtein_distance(text_emotion, emotion)
                    max_len = max(len(text_emotion), len(emotion))
                    similarity = 1 - (distance / max_len if max_len > 0 else 0)
                    if similarity > similarity_limit:
                        max_similarity = similarity
                        best_matching_emotion = emotion
                        emoji_similarities.append((emoji, max_similarity, best_matching_emotion))
            emoji_similarities.sort(key=lambda x: x[1], reverse=True)
            top_emojis = emoji_similarities[:10] if len(emoji_similarities) > 10 else emoji_similarities
            logger.info(
                f"为[{text_emotion}]找到 {len(top_emojis)} 个匹配的表情包，前10: {[(e[0].emotion, e[1]) for e in top_emojis]}"
            )
            if not top_emojis:
                logger.warning("未找到匹配的表情包")
                return None
            selected_emoji, similarity, matched_emotion = random.choice(top_emojis)
            self.record_usage(selected_emoji.hash)
            logger.info(
                f"为[{text_emotion}]找到表情包: {matched_emotion} ({selected_emoji.filename}), Similarity: {similarity:.4f}"
            )
            return selected_emoji.full_path, f"[ {selected_emoji.description} ]"
        except Exception as e:
            logger.error(f"[错误] 获取表情包失败: {str(e)}")
            return None
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]
    async def check_emoji_file_integrity(self) -> None:
        try:
            if not self.emoji_objects:
                logger.warning("[检查] emoji_objects为空，跳过完整性检查")
                return
            total_count = len(self.emoji_objects)
            self.emoji_num = total_count
            removed_count = 0
            objects_to_remove = []
            for emoji in self.emoji_objects:
                try:
                    if emoji.is_deleted:
                        objects_to_remove.append(emoji)
                        continue
                    if not os.path.exists(emoji.full_path):
                        logger.warning(f"[检查] 表情包文件丢失: {emoji.full_path}")
                        await emoji.delete()
                        objects_to_remove.append(emoji)
                        self.emoji_num -= 1
                        removed_count += 1
                        continue
                    if not emoji.description:
                        logger.warning(f"[检查] 表情包描述为空，视为无效: {emoji.filename}")
                        await emoji.delete()
                        objects_to_remove.append(emoji)
                        self.emoji_num -= 1
                        removed_count += 1
                        continue
                except Exception as item_error:
                    logger.error(f"[错误] 处理表情包记录时出错 ({emoji.filename}): {str(item_error)}")
                    continue
            if objects_to_remove:
                self.emoji_objects = [e for e in self.emoji_objects if e not in objects_to_remove]
                _save_all_emoji_objects(self.emoji_objects)
            await clean_unused_emojis(EMOJI_REGISTED_DIR, self.emoji_objects)
            if removed_count > 0:
                logger.info(f"[清理] 已清理 {removed_count} 个失效/文件丢失的表情包记录")
                logger.info(f"[统计] 清理前记录数: {total_count} | 清理后有效记录数: {len(self.emoji_objects)}")
            else:
                logger.info(f"[检查] 已检查 {total_count} 个表情包记录，全部完好")
        except Exception as e:
            logger.error(f"[错误] 检查表情包完整性失败: {str(e)}")
            logger.error(traceback.format_exc())


    async def start_periodic_check_register(self) -> None:
        """
        定时扫描表情包目录，检查表情包完整性并注册新表情包
        """

        await self.get_all_emoji_from_json()
        while True:
            logger.info("[扫描] 开始检查表情包完整性...")
            await self.check_emoji_file_integrity()
            await clear_temp_emoji()
            logger.info("[扫描] 开始扫描新表情包...")
            if not os.path.exists(EMOJI_APPROVED_DIR):
                logger.warning(f"[警告] 表情包目录不存在: {EMOJI_APPROVED_DIR}")
                os.makedirs(EMOJI_APPROVED_DIR, exist_ok=True)
                logger.info(f"[创建] 已创建表情包目录: {EMOJI_APPROVED_DIR}")
                await asyncio.sleep(global_config.emoji.check_interval * 60)
                continue
            files = os.listdir(EMOJI_APPROVED_DIR)
            if not files:
                logger.warning("无新表情包文件，等待下一次扫描...")
                await asyncio.sleep(global_config.emoji.check_interval * 60)
                continue
            if (self.emoji_num > self.emoji_num_max and global_config.emoji.do_replace) or (
                self.emoji_num < self.emoji_num_max
            ):
                try:
                    files_to_process = [
                        f
                        for f in files
                        if os.path.isfile(os.path.join(EMOJI_APPROVED_DIR, f))
                        and f.lower().endswith((".jpg", ".jpeg", ".png", ".gif"))
                    ]
                    for filename in files_to_process:
                        success = await self.register_emoji_by_filename(filename)
                        if success:
                            # break
                            continue
                        else:
                            file_path = os.path.join(EMOJI_APPROVED_DIR, filename)
                            os.remove(file_path)
                            logger.warning(f"[清理] 删除注册失败的表情包文件: {filename}")
                except Exception as e:
                    logger.error(f"[错误] 扫描表情包目录失败: {str(e)}")
            await asyncio.sleep(global_config.emoji.check_interval * 60)
    async def get_all_emoji_from_json(self) -> None:
        try:
            self._ensure_db()
            logger.debug("[json] 开始加载所有表情包记录 ...")
            emoji_objects = _load_all_emoji_objects()
            self.emoji_objects = emoji_objects
            self.emoji_num = len(emoji_objects)
            logger.info(f"[json] 加载完成: 共加载 {self.emoji_num} 个表情包记录。")
        except Exception as e:
            logger.error(f"从json加载所有表情包对象失败: {str(e)}")
            self.emoji_objects = []
            self.emoji_num = 0
    async def get_emoji_from_manager(self, emoji_hash: str) -> Optional["MaiEmoji"]:
        for emoji in self.emoji_objects:
            if not emoji.is_deleted and emoji.hash == emoji_hash:
                return emoji
        return None
    async def delete_emoji(self, emoji_hash: str) -> bool:
        try:
            self._ensure_db()
            emoji = await self.get_emoji_from_manager(emoji_hash)
            if not emoji:
                logger.warning(f"[警告] 未找到哈希值为 {emoji_hash} 的表情包")
                return False
            success = await emoji.delete()
            if success:
                self.emoji_objects = [e for e in self.emoji_objects if e.hash != emoji_hash]
                self.emoji_num -= 1
                _save_all_emoji_objects(self.emoji_objects)
                logger.info(f"[统计] 当前表情包数量: {self.emoji_num}")
                return True
            else:
                logger.error(f"[错误] 删除表情包失败: {emoji_hash}")
                return False
        except Exception as e:
            logger.error(f"[错误] 删除表情包失败: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    async def replace_a_emoji(self, new_emoji: "MaiEmoji") -> bool:
        try:
            self._ensure_db()
            emoji_objects = self.emoji_objects
            probabilities = [1 / (emoji.usage_count + 1) for emoji in emoji_objects]
            total_probability = sum(probabilities)
            normalized_probabilities = [p / total_probability for p in probabilities]
            selected_emojis = random.choices(
                emoji_objects, weights=normalized_probabilities, k=min(MAX_EMOJI_FOR_PROMPT, len(emoji_objects))
            )
            emoji_info_list = _emoji_objects_to_readable_list(selected_emojis)
            prompt = (
                f"{global_config.bot.nickname}的表情包存储已满({self.emoji_num}/{self.emoji_num_max})，"
                f"需要决定是否删除一个旧表情包来为新表情包腾出空间。\n\n"
                f"新表情包信息：\n"
                f"描述: {new_emoji.description}\n\n"
                f"现有表情包列表：\n" + "\n".join(emoji_info_list) + "\n\n"
                "请决定：\n"
                "1. 是否要删除某个现有表情包来为新表情包腾出空间？\n"
                "2. 如果要删除，应该删除哪一个(给出编号)？\n"
                "请只回答：'不删除'或'删除编号X'(X为表情包编号)。"
            )
            decision, _ = await self.llm_emotion_judge.generate_response_async(prompt, temperature=0.8)
            logger.info(f"[决策] 结果: {decision}")
            if "不删除" in decision:
                logger.info("[决策] 不删除任何表情包")
                return False
            match = re.search(r"删除编号(\d+)", decision)
            if match:
                emoji_index = int(match.group(1)) - 1
                if 0 <= emoji_index < len(selected_emojis):
                    emoji_to_delete = selected_emojis[emoji_index]
                    logger.info(f"[决策] 删除表情包: {emoji_to_delete.description}")
                    delete_success = await self.delete_emoji(emoji_to_delete.hash)
                    if delete_success:
                        register_success = await new_emoji.register_to_json()
                        if register_success:
                            self.emoji_objects.append(new_emoji)
                            self.emoji_num += 1
                            _save_all_emoji_objects(self.emoji_objects)
                            logger.info(f"[成功] 注册: {new_emoji.filename}")
                            return True
                        else:
                            logger.error(f"[错误] 注册表情包到json失败: {new_emoji.filename}")
                            return False
                    else:
                        logger.error("[错误] 删除表情包失败，无法完成替换")
                        return False
                else:
                    logger.error(f"[错误] 无效的表情包编号: {emoji_index + 1}")
            else:
                logger.error(f"[错误] 无法从决策中提取表情包编号: {decision}")
            return False
        except Exception as e:
            logger.error(f"[错误] 替换表情包失败: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    async def build_emoji_description(self, image_base64: str) -> Tuple[str, List[str]]:
        """
        使用img_request.analyze_emotion_from_image分析表情包描述和情感标签
        """
        try:
            # 将base64转为图片临时文件
            image_bytes = base64.b64decode(image_base64)
            temp_path = os.path.join(EMOJI_APPROVED_DIR, f"temp_{int(time.time()*1000)}.jpg")
            with open(temp_path, "wb") as f:
                f.write(image_bytes)
            description, emotions = await analyze_emotion_from_image(temp_path)
            os.remove(temp_path)
            return description, emotions
        except Exception as e:
            logger.error(f"获取表情包描述失败: {str(e)}")
            logger.error(traceback.format_exc())
            return "", []

    async def register_emoji_by_filename(self, filename: str) -> bool:
        file_full_path = os.path.join(EMOJI_APPROVED_DIR, filename)
        if not os.path.exists(file_full_path):
            logger.error(f"[注册失败] 文件不存在: {file_full_path}")
            return False
        try:
            new_emoji = MaiEmoji(full_path=file_full_path)
            init_result = await new_emoji.initialize_hash_format()
            if init_result is None or new_emoji.is_deleted:
                logger.error(f"[注册失败] 初始化哈希和格式失败: {filename}")
                return False
            if await self.get_emoji_from_manager(new_emoji.hash):
                logger.warning(f"[注册失败] 已存在相同哈希的表情包: {filename}")
                return False
            # 获取base64
            image_base64 = image_path_to_base64(file_full_path)
            description, emotions = await self.build_emoji_description(image_base64)
            new_emoji.description = description
            new_emoji.emotion = emotions
            register_success = await new_emoji.register_to_json()
            if register_success:
                self.emoji_objects.append(new_emoji)
                self.emoji_num += 1
                _save_all_emoji_objects(self.emoji_objects)
                logger.info(f"[成功] 注册: {new_emoji.filename}")
                return True
            else:
                logger.error(f"[错误] 注册表情包到json失败: {new_emoji.filename}")
                return False
        except Exception as e:
            logger.error(f"[注册失败] 发生异常: {str(e)}")
            logger.error(traceback.format_exc())
            return False

# emoji_manager 包初始化
# 移除本地 emoji_manager 实例，避免与 manager.py 冲突
