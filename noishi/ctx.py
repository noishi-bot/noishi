import asyncio
from collections import defaultdict
from typing import Callable, Type, Optional, Union, Any, TypeAlias, get_args, overload
import inspect
import functools
import types
from abc import ABC, abstractmethod
import importlib
from noishi.exception import SubModuleInjectError, SubModuleNoExistApplyError, SubModuleApplyArgsError

# ---------------------- Event & Service ----------------------
class Event:
    pass

class Service(ABC):
    def __init__(self, ctx: 'Context'):
        self.ctx = ctx

    @abstractmethod
    def unregister(self) -> None:
        pass

handler_type: TypeAlias = Union[Service, Callable[..., Any], 'Context', Any]

# ---------------------- Context ----------------------
class Context:
    def __init__(self):
        self._handler: dict[str, handler_type] = {}
        self._event_handler: dict[Type[Event], list[Callable]] = defaultdict(list)
        self._module_info: dict[str, dict[str,Union[types.ModuleType,list,tuple,dict]]] = {}  # module_name -> {"module": module, "names": [], "args":(), "kwargs":{}}
        self._tracking_module: Optional[str] = None

    @overload
    def register(self, name: str) -> 'Context': 
        "创建并注册子Context。"
        pass
    
    @overload
    def register(self, name: str, handler: Callable[..., Any]) -> 'Context': 
        "注册函数。"
        pass
    
    @overload
    def register(self, name: str, handler: 'Context') -> 'Context': 
        "注册子Context。"
        pass
    
    @overload
    def register(self, name: str, handler: Any) -> 'Context': 
        "注册对象。"
        pass
    
    def register(self, name: str, handler: Optional[handler_type] = None) -> 'Context':
        if name in self._handler:
            raise ValueError(f"已有同名对象 '{name}' 注册。")
        
        result = handler if handler is not None else Context()
        self._handler[name] = result

        if self._tracking_module:
            self._module_info[self._tracking_module]["names"].append(name)

        return result if handler is not None else result

    def get(self, path: str) -> handler_type:
        "通过路径获取对象。"
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
        if name in self._handler:
            return self._handler[name]
        raise AttributeError(f"没有名为 '{name}' 的对象。")

    def unregister(self, name: str | None = None) -> None:
        "注销对象。"
        if name is None:
            for key in list(self._handler.keys()):
                self.unregister(key)
            return None

        if name not in self._handler:
            raise ValueError(f"没有名为 '{name}' 的对象可以注销。")
        
        handler = self._handler[name]

        if isinstance(handler, Context):
            handler.unregister()

        elif hasattr(handler, "unregister") and callable(handler.unregister):
            handler.unregister()

        del self._handler[name]

    def reload(self, name: str, handler: handler_type) -> 'Context':
        "重载对象。"
        if name in self._handler:
            self.unregister(name)
        return self.register(name, handler)

    def register_event_handler(self, func: Callable) -> Callable:
        "注册事件处理器"
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("事件处理器必须是异步函数。")

        sig = inspect.signature(func)
        param_events = {}

        for pname, param in sig.parameters.items():
            anno = param.annotation
            is_optional = False

            origin = getattr(anno, '__origin__', None)
            args_ = get_args(anno)
            if origin is Union and type(None) in args_:
                real_type = next(t for t in args_ if t is not type(None))
                is_optional = True
            else:
                real_type = anno

            if isinstance(real_type, type) and issubclass(real_type, Event):
                param_events[pname] = (real_type, is_optional)

        async def wrapper(*events, **kwargs):
            def type_depth(t: type) -> int:
                return len(inspect.getmro(t))

            params = sorted(param_events.items(), key=lambda item: type_depth(item[1][0]), reverse=True)
            mappings = []

            def backtrack(i: int, current_bind: dict[str, Event | None], used: set[int]):
                if i >= len(params):
                    mappings.append(current_bind.copy())
                    return
                pname, (ptype, optional) = params[i]
                candidates = [idx for idx, e in enumerate(events) if idx not in used and isinstance(e, ptype)]
                for idx in candidates:
                    current_bind[pname] = events[idx]
                    used.add(idx)
                    backtrack(i + 1, current_bind, used)
                    used.remove(idx)
                    del current_bind[pname]
                if optional and not candidates:
                    current_bind[pname] = None
                    backtrack(i + 1, current_bind, used)
                    del current_bind[pname]

            backtrack(0, {}, set())
            tasks = [asyncio.create_task(func(**bind)) for bind in mappings] if mappings else []
            if tasks:
                await asyncio.gather(*tasks)

        wrapper = functools.wraps(func)(wrapper)

        for et in {ptype for ptype, _ in param_events.values()}:
            if et not in self._event_handler:
                self._event_handler[et] = []
            self._event_handler[et].append(wrapper)

        return func

    def unregister_event_handler(self, func: Callable) -> None:
        "注销事件处理器"
        found = [(et, cb) for et, listeners in self._event_handler.items()
                 for cb in listeners if getattr(cb, '__wrapped__', None) == func]
        if not found:
            raise ValueError(f"事件处理器 {func.__name__} 没有注册。")
        for et, cb in found:
            self._event_handler[et].remove(cb)
        self._event_handler = {k: v for k, v in self._event_handler.items() if v}

    async def send_event(self, *events: Event) -> None:
        "发送事件。"
        seen = set()
        tasks = []
        for event in events:
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
        "添加子模块。"
        func = getattr(module, "apply", None)
        if not callable(func):
            raise SubModuleNoExistApplyError(f"模块 {module.__name__} 未实现 apply。")
        if not self.check_sub_module_inject(module):
            raise SubModuleInjectError(f"模块 {module.__name__} inject 未满足。")

        self._tracking_module = module.__name__
        self._module_info[module.__name__] = {"module": module, "names": [], "args": args, "kwargs": kwargs}

        try:
            func(self, *args, **kwargs)
        except TypeError as e:
            raise SubModuleApplyArgsError(f"调用模块 {module.__name__}.apply 时参数错误: {e}")
        finally:
            self._tracking_module = None

        return [self._handler[name] for name in self._module_info[module.__name__]["names"]]

    def check_sub_module_inject(self, module: types.ModuleType) -> bool:
        "检查子模块inject。"
        inject = getattr(module, "inject", None)
        if isinstance(inject, list):
            return all(k in self._handler for k in inject)
        return True

    def reload_sub_module(self, module_name: str, *args, **kwargs) -> Any:
        "重载子模块。"
        if module_name not in self._module_info:
            raise ValueError(f"模块 {module_name} 未注册，无法重载。")
        
        info = self._module_info[module_name]

        for name in info["names"]:
            if name in self._handler:
                self.unregister(name)

        reloaded_module = importlib.reload(info["module"])
        self._module_info[module_name]["module"] = reloaded_module
        
        use_args = args if args else info["args"]
        use_kwargs = kwargs if kwargs else info["kwargs"]

        return self.add_sub_module(reloaded_module, *use_args, **use_kwargs)