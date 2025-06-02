# src/common/logger_manager.py
import os
import logging
from logging.handlers import TimedRotatingFileHandler
import sys

def get_logger(logger_name: str) -> logging.Logger:
    """创建并配置日志记录器
    
    Args:
        logger_name: 日志记录器名称
    
    Returns:
        配置好的日志记录器实例
    """
    # 确保日志目录存在
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    # 创建日志记录器
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    
    # 检查是否已配置处理器（避免重复添加）
    if not logger.handlers:
        # 设置日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        try:
            # 创建按天滚动的文件处理器
            file_handler = TimedRotatingFileHandler(
                filename=os.path.join(log_dir, f"{logger_name}.log"),
                when="midnight",
                interval=1,
                backupCount=7,
                encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.INFO)
            logger.addHandler(file_handler)
        except Exception as e:
            sys.stderr.write(f"创建文件日志处理器失败: {str(e)}\n")
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)
        logger.addHandler(console_handler)
    
    # 禁止日志传播到根记录器
    logger.propagate = False
    
    return logger
