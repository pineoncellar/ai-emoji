from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from .routes import router as api_router
from src.emoji_manager.manager import emoji_manager
import asyncio

# 使用 Lifespan 事件处理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理应用的生命周期事件"""
    # 启动时初始化表情包管理器
    try:
        # 检查 emoji_manager 实例和方法
        print(f"emoji_manager type: {type(emoji_manager)}")
        print(f"emoji_manager.initialize: {getattr(emoji_manager, 'initialize', None)}")
        if not hasattr(emoji_manager, "initialize") or not callable(emoji_manager.initialize):
            raise RuntimeError("emoji_manager 未正确初始化或缺少 initialize 方法")
        # 初始化表情包信息
        await emoji_manager.initialize()

        # 启动定时任务
        task = asyncio.create_task(emoji_manager.start_periodic_check_register())
        print("✅ 表情包管理器初始化完成")
        
        # 应用运行中
        yield
        
        # 应用关闭时
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        print("🛑 表情包管理器已关闭")
    except Exception as e:
        print(f"❌ 表情包管理器初始化失败: {str(e)}")
        raise

app = FastAPI(
    title="表情包管理API",
    description="提供表情包的上报、审核、注册和匹配服务",
    version="1.0.0",
    lifespan=lifespan
)

# 挂载API路由
app.include_router(api_router, prefix="/api/emoji")

# 挂载静态文件路由
app.mount("/preview/unreviewed", StaticFiles(directory="data/emoji_unreviewed"), name="unreviewed")
app.mount("/preview/approved", StaticFiles(directory="data/emoji_approved"), name="approved")
