# ai_emoji

以 api 接口形式由 ai 的发言检索表情包

核心代码来源：[MaiBot](https://github.com/MaiM-with-u/MaiBot)

# 使用方法

程序需要用到两个模型，一个识图模型用于识图，一个通用模型用于文本情感提取。
在`config.yaml`中填入`base_url`和`api_ket`，再填入对应的模型名称即可。

# 接口介绍

> 目前仅支持 POST 方法，`Content-Type = application/json`.

### `/api/emoji/upload`

上传图片接口，目前仅支持图片链接形式

上传的图片会被放在`data/emoji_unreviewed`文件夹，需要手动审核合适的表情包放进`data/emoji_approved`内，程序会根据配置文件的`emoji.check_interval`配置定时扫描注册表情包。

示例请求：

```json
{
  "image_url": "www.xxxxx.com"
}
```

示例响应：

```json
{
  "status": "ok",
  "message": "图片已保存待审核"
}
```

### `/api/emoji/match`

上传发言接口，程序根据发言做情感提取，自动匹配合适的表情包。

示例请求：

```json
{
  "text": "哇袄"
}
```

示例响应：

```json
{
  "status": "ok",
  "text": "哇袄",
  "emoji_path": "data/emoji_registed/xxxxxxxxxxxx.jpg",
  "description": "这张表情包展现了一个可爱的卡通角色，其表情和动作传递了一种轻松、愉悦和略带羞涩的情感。以下是对表情包情感和内容的详细分析：\n\n1. **角色形象**：\n   - 角色是一个卡通人物，穿着带有十字标志的服装，可能暗示医疗或治愈的主题。\n   - 角色有金色的头发，戴着帽子，表情是微笑并闭着眼睛，显得非常开心和满足。\n\n2. **表情符号**：\n   - 角色脸颊泛红，表现出害羞或兴奋的情绪。\n   - 头顶的心形符号和“S”形符号，通常用于表示喜爱或喜欢，进一步强化了角色愉悦和满足的情绪。\n\n3. **互联网梗**：\n   - 这个表情包可能来源于某个游戏或动漫角色，通常用于表达对某事物的喜爱或欣赏。\n   - 在互联网上，这种表情包可能被用来调侃或表达对某人或某事的喜爱，带有一种轻松幽默的意味。\n\n4. **使用场景**：\n   - 在聊天中，可以用来表示对某人的欣赏或对某件事的喜爱。\n   - 也可以用于表达一种轻松愉快的心情，比如对美食、美景等的赞美。\n\n总结来说，这张表情包通过卡通形象和符号的结合，传递出一种轻松、愉悦和略带羞涩的情感，常用于表达对某人或某事的喜爱或欣赏。",
  "base64": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

## To do list

- 自定义 host 与 port
- 识别图像格式
- 支持 get 方法
- 更多审核方式

~~虽然都不难写但是没时间，有空再说 x~~
