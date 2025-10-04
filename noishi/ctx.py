import asyncio
from collections import defaultdict
from typing import Callable, Type, Optional, Union, Any, TypeAlias, get_args
import inspect
import functools
import types
from abc import ABC, abstractmethod
import importlib
from noishi.exception import SubModuleInjectError, SubModuleNoExistApplyError, SubModuleApplyArgsError

# ---------------------- 事件与服务基类 ----------------------
class Event:
    """事件基类，所有自定义事件都应继承此类"""
    pass

class Service(ABC):
    """服务基类，提供统一的生命周期管理"""
    def __init__(self, ctx: 'Context'):
        self.ctx = ctx  # 持有上下文引用

    @abstractmethod
    def unregister(self) -> None:
        """抽象方法，服务注销时的清理逻辑"""
        pass

# 处理器类型别名，可以是服务、回调函数、上下文或其他任意对象
handler_type: TypeAlias = Union['Service', Callable[..., Any], 'Context', Any]

# ---------------------- 上下文核心类 ----------------------
class Context:
    """依赖注入容器和事件总线"""
    
    def __init__(self):
        # 注册的处理器字典：名称 -> 处理器对象
        self._handler: dict[str, handler_type] = {}
        # 事件处理器字典：事件类型 -> 回调函数列表
        self._event_handler: dict[Type[Event], list[Callable]] = defaultdict(list)
        # 模块信息记录：模块名 -> 模块元数据
        self._module_info: dict[str, dict[str,Union[types.ModuleType,list,tuple,dict]]] = {}
        # 当前正在跟踪的模块名（用于自动记录注册的对象）
        self._tracking_module: Optional[str] = None

    def register(self, name: str, handler: Optional[handler_type] = None) -> 'Context':
        """注册处理器对象，如果handler为None则创建子上下文"""
        if name in self._handler:
            raise ValueError(f"已有同名对象 '{name}' 注册。")
        
        # 如果未提供处理器，创建新的子上下文
        result = handler if handler is not None else Context()
        self._handler[name] = result

        # 如果正在跟踪模块，记录此注册的对象
        if self._tracking_module:
            self._module_info[self._tracking_module]["names"].append(name)

        return result if handler is not None else result

    def get(self, path: str) -> handler_type:
        """通过路径获取处理器对象，支持点分隔的嵌套访问"""
        parts = path.split('.', 1)
        key = parts[0]
        if key not in self._handler:
            raise ValueError(f"没有名为 '{key}' 的对象。")
        
        handler = self._handler[key]

        if len(parts) == 1:
            return handler
        else:
            if not isinstance(handler, Context):
                raise ValueError(f"'{key}' 不是子上下文，无法访问 '{parts[1]}'")
            return handler.get(parts[1])

    def __getattr__(self, name: str) -> handler_type:
        """通过属性访问方式获取处理器"""
        if name in self._handler:
            return self._handler[name]
        raise AttributeError(f"没有名为 '{name}' 的对象。")

    def unregister(self, name: str | None = None) -> None:
        """注销处理器，支持递归注销所有对象"""
        if name is None:
            # 注销所有处理器
            for key in list(self._handler.keys()):
                self.unregister(key)
            return None

        if name not in self._handler:
            raise ValueError(f"没有名为 '{name}' 的对象可以注销。")
        
        handler = self._handler[name]

        # 递归注销子上下文
        if isinstance(handler, Context):
            handler.unregister()
        # 调用服务的注销方法
        elif hasattr(handler, "unregister") and callable(handler.unregister):
            handler.unregister()

        del self._handler[name]

    def reload(self, name: str, handler: handler_type) -> 'Context':
        """重新加载处理器（先注销再注册）"""
        if name in self._handler:
            self.unregister(name)
        return self.register(name, handler)

    def register_event_handler(self, func: Callable) -> Callable:
        """注册事件处理器装饰器"""
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("事件处理器必须是异步函数。")

        # 分析函数参数，找出事件类型
        sig = inspect.signature(func)
        param_events = {}

        for pname, param in sig.parameters.items():
            anno = param.annotation
            is_optional = False

            # 处理 Optional[Event] 类型注解
            origin = getattr(anno, '__origin__', None)
            args_ = get_args(anno)
            if origin is Union and type(None) in args_:
                real_type = next(t for t in args_ if t is not type(None))
                is_optional = True
            else:
                real_type = anno

            # 记录事件参数
            if isinstance(real_type, type) and issubclass(real_type, Event):
                param_events[pname] = (real_type, is_optional)

        # 创建包装器，实现事件参数自动绑定
        async def wrapper(*events, **kwargs):
            def type_depth(t: type) -> int:
                """计算类型的继承深度，用于优先级排序"""
                return len(inspect.getmro(t))

            # 按继承深度排序参数（从深到浅）
            params = sorted(param_events.items(), key=lambda item: type_depth(item[1][0]), reverse=True)
            mappings = []

            # 回溯算法匹配事件到参数
            def backtrack(i: int, current_bind: dict[str, Event | None], used: set[int]):
                if i >= len(params):
                    mappings.append(current_bind.copy())
                    return
                pname, (ptype, optional) = params[i]
                # 寻找匹配的事件对象
                candidates = [idx for idx, e in enumerate(events) if idx not in used and isinstance(e, ptype)]
                for idx in candidates:
                    current_bind[pname] = events[idx]
                    used.add(idx)
                    backtrack(i + 1, current_bind, used)
                    used.remove(idx)
                    del current_bind[pname]
                # 处理可选参数
                if optional and not candidates:
                    current_bind[pname] = None
                    backtrack(i + 1, current_bind, used)
                    del current_bind[pname]

            backtrack(0, {}, set())
            # 为每种匹配组合创建任务
            tasks = [asyncio.create_task(func(**bind)) for bind in mappings] if mappings else []
            if tasks:
                await asyncio.gather(*tasks)

        wrapper = functools.wraps(func)(wrapper)

        # 注册包装器到对应的事件类型
        for et in {ptype for ptype, _ in param_events.values()}:
            if et not in self._event_handler:
                self._event_handler[et] = []
            self._event_handler[et].append(wrapper)

        return func

    def unregister_event_handler(self, func: Callable) -> None:
        """注销事件处理器"""
        found = [(et, cb) for et, listeners in self._event_handler.items()
                 for cb in listeners if getattr(cb, '__wrapped__', None) == func]
        if not found:
            raise ValueError(f"事件处理器 {func.__name__} 没有注册。")
        for et, cb in found:
            self._event_handler[et].remove(cb)
        # 清理空的事件处理器列表
        self._event_handler = {k: v for k, v in self._event_handler.items() if v}

    async def send_event(self, *events: Event) -> None:
        """发送事件，自动调用匹配的事件处理器"""
        seen = set()
        tasks = []
        for event in events:
            # 遍历事件的所有父类
            for et in inspect.getmro(type(event)):
                if et is object:
                    break
                for cb in self._event_handler.get(et, []):
                    if cb not in seen:
                        seen.add(cb)
                        tasks.append(asyncio.create_task(cb(*events)))
        if tasks:
            await asyncio.gather(*tasks)

    def add_sub_module(self, module: types.ModuleType, *args, **kwargs):
        """添加子模块，自动调用模块的apply函数"""
        func = getattr(module, "apply", None)
        if not callable(func):
            raise SubModuleNoExistApplyError(f"模块 {module.__name__} 未实现 apply。")
        # 检查依赖注入要求
        if not self.check_sub_module_inject(module):
            raise SubModuleInjectError(f"模块 {module.__name__} inject 未满足。")

        # 开始跟踪模块注册的对象
        self._tracking_module = module.__name__
        self._module_info[module.__name__] = {"module": module, "names": [], "args": args, "kwargs": kwargs}

        try:
            # 调用模块的apply函数
            func(self, *args, **kwargs)
        except TypeError as e:
            raise SubModuleApplyArgsError(f"调用模块 {module.__name__}.apply 时参数错误: {e}")
        finally:
            self._tracking_module = None

        return [self._handler[name] for name in self._module_info[module.__name__]["names"]]

    def check_sub_module_inject(self, module: types.ModuleType) -> bool:
        """检查模块的依赖注入要求是否满足"""
        inject = getattr(module, "inject", None)
        if isinstance(inject, list):
            return all(k in self._handler for k in inject)
        return True

    def reload_sub_module(self, module_name: str, *args, **kwargs) -> Any:
        """重新加载子模块"""
        if module_name not in self._module_info:
            raise ValueError(f"模块 {module_name} 未注册，无法重载。")
        
        info = self._module_info[module_name]

        # 清理模块之前注册的对象
        for name in info["names"]:
            if name in self._handler:
                self.unregister(name)

        # 重新加载模块
        reloaded_module = importlib.reload(info["module"])
        self._module_info[module_name]["module"] = reloaded_module
        
        # 使用新参数或原有参数
        use_args = args if args else info["args"]
        use_kwargs = kwargs if kwargs else info["kwargs"]

        return self.add_sub_module(reloaded_module, *use_args, **use_kwargs)