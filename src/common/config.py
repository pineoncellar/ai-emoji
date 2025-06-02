"""
全局配置模块，支持从config.yaml读取参数。
"""
from typing import Any
from pydantic import BaseModel
import yaml
import os

class EmojiConfig(BaseModel):
    check_interval: float = 10.0  # 扫描间隔（分钟），支持小数
    max_reg_num: int = 100  # 最大注册表情包数量
    do_replace: bool = False  # 达到最大数量后是否替换
    content_filtration: bool = True  # 是否进行内容过滤
    filtration_prompt: str = "健康、积极、符合社区规范的内容"  # 过滤提示词
    # 可扩展更多emoji相关配置

class ModelConfig(BaseModel):
    vlm: str = ""  # VLM模型名称
    utils: str = ""  # 通用模型名称
    base_url: str = ""  # API基础URL
    api_key: str = ""  # API密钥
    max_token: int = 2048  # 模型最大输出长度
    # 可扩展更多模型相关配置

class BotConfig(BaseModel):
    nickname: str = "AI表情助手"  # 机器人昵称

class GlobalConfig(BaseModel):
    emoji: EmojiConfig = EmojiConfig()
    model: ModelConfig = ModelConfig()
    bot: BotConfig = BotConfig()
    # 可扩展更多全局配置

def load_config_from_yaml(yaml_path: str = None) -> GlobalConfig:
    if yaml_path is None:
        yaml_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config.yaml")
    if not os.path.exists(yaml_path):
        return GlobalConfig()
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    emoji_conf = data.get("emoji", {})
    model_conf = data.get("model", {})
    bot_conf = data.get("bot", {})
    
    return GlobalConfig(
        emoji=EmojiConfig(**emoji_conf),
        model=ModelConfig(
            **model_conf
        ),
        bot=BotConfig(**bot_conf)
    )

global_config = load_config_from_yaml()
