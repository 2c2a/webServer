# 08 - 插件系统

## 架构

```
PluginInterface（抽象基类）
├── initialize() / shutdown()      # 必须实现的异步生命周期
│
├── RouteProvider                  # 提供 FastAPI 路由
├── ServiceProvider                # 注册可复用服务
├── UIExtensionProvider            # 注册 JinjaX 组件扩展点
└── EventHook                      # 事件钩子（async emit 并发执行）
```

## 插件目录结构

```
app/plugins/<plugin_id>/
├── __init__.py      # 导出插件类
└── plugin.py        # 插件实现
```

## 创建插件

```python
# app/plugins/my_plugin/plugin.py
from app.plugins.base import PluginInterface, RouteProvider
import fastapi

class MyPlugin(PluginInterface, RouteProvider):
    def __init__(self):
        super().__init__(
            plugin_id="my_plugin",
            name="我的插件",
            version="0.1.0",
            description="示例插件",
        )

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    def get_routes(self) -> tuple[str, fastapi.APIRouter]:
        router = fastapi.APIRouter()
        @router.get("/hello")
        async def hello():
            return {"message": "Hello"}
        return ("/my_plugin", router)
```

## 生命周期

```
应用启动 → PluginLoader.load_discovered()
         → 遍历 app/plugins/*/plugin.py
         → 实例化 → on_load() → initialize()
         → 注册路由/服务/UI 扩展
应用关闭 → shutdown() → on_unload()
```

## CLI 管理

```bash
2c2a plugin list                 # 列出插件
2c2a plugin info <plugin_id>     # 详情
2c2a plugin enable <plugin_id>   # 启用
2c2a plugin disable <plugin_id>  # 禁用
2c2a plugin reload               # 重新加载
2c2a plugin routes               # 查看所有路由
2c2a plugin scaffold <id>        # 生成骨架
```

## 规范

1. plugin_id 小写 + 下划线，与目录名一致
2. 所有生命周期方法必须是 async
3. 路由前缀以插件 ID 开头，避免冲突
4. 插件中的数据查询必须遵守站点隔离
5. 静态资源放 `app/plugins/<id>/static/`，`collectstatic` 收集