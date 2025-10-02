import asyncio
from collections import defaultdict
from typing import Callable, Type, get_args, Union, Optional, overload, TypeAlias, Any
import inspect
import functools
import types
from noishi.exception import SubModuleInjectError, SubModuleNoExistApplyError

handler_type: TypeAlias = Union[Callable[..., Any], 'Context', Any]

class Event:
    pass

class Context:
    def __init__(self):
        self._handler: dict[str, handler_type] = {}
        self._event_handler: dict[Type[Event], list[Callable]] = defaultdict(list)

    @overload
    def register(self, name: str, handler: Callable) -> 'Context':
        "注册一个处理器到当前上下文。"
        ...
    
    @overload
    def register(self, name: str, handler: 'Context') -> 'Context':
        "注册一个子上下文到当前上下文。"
        ...
        
    @overload
    def register(self, name: str, handler: Any) -> 'Context':
        "注册一个对象到当前上下文。(不推荐)"
        ...

    @overload
    def register(self, name: str) -> 'Context':
        "新建一个子上下文。"
        ...

    def register(self, name: str, handler: Optional[handler_type] = None) -> 'Context':
        if name in self._handler:
            raise ValueError("已有同名对象注册。")
        
        if handler is None:
            subctx = Context()
            self._handler[name] = subctx
            return subctx
        else:
            self._handler[name] = handler
            return self

    def get(self, path: str) -> handler_type:
        "获取当前上下文中指定的对象"
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

    def unregister(self, name: str) -> None:
        "注销当前上下文中指定对象。"
        if name in self._handler:
            del self._handler[name]
        else:
            raise ValueError(f"没有名为 '{name}' 的处理器可以注销。")

    def __getattr__(self, name: str) -> handler_type | None:
        if name in self._handler:
            return self._handler[name]
        raise AttributeError(f"没有名为 '{name}' 的对象。")

    def register_event_handler(self, func: Callable) -> Callable:
        "注册一个事件处理器函数。"
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("注册的事件处理器必须是异步函数。")

        sig = inspect.signature(func)
        param_events = {}

        for name, param in sig.parameters.items():
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
                param_events[name] = (real_type, is_optional)

        async def wrapper(*events, **kwargs):
            def type_depth(t: type) -> int:
                return len(inspect.getmro(t))

            params = list(param_events.items())
            params.sort(key=lambda item: type_depth(item[1][0]), reverse=True)

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

            if not mappings:
                return

            tasks = [asyncio.create_task(func(**bind)) for bind in mappings]
            if tasks:
                await asyncio.gather(*tasks)

        wrapper = functools.wraps(func)(wrapper)

        for et in {ptype for ptype, _ in param_events.values()}:
            self._event_handler[et].append(wrapper)

        return func

    def unregister_event_handler(self, func: Callable) -> None:
        "注销指定的事件处理器函数。"
        found_callbacks = [
            (et, cb)
            for et, listeners in self._event_handler.items()
            for cb in listeners
            if getattr(cb, '__wrapped__', None) == func
        ]

        if not found_callbacks:
            raise ValueError(f"事件处理器 {func.__name__} 没有注册。")

        for et, cb in found_callbacks:
            self._event_handler[et].remove(cb)

        self._event_handler = {k: v for k, v in self._event_handler.items() if v}

    async def send_event(self, *events: Event) -> None:
        "发送事件到事件处理器。"
        seen = set()
        tasks = []

        for event in events:
            for et in inspect.getmro(type(event)):
                if et is object:
                    break
                for callback in self._event_handler.get(et, []):
                    if callback not in seen:
                        seen.add(callback)
                        tasks.append(asyncio.create_task(callback(*events)))

        if tasks:
            await asyncio.gather(*tasks)
    
    def add_sub_module(self, module: types.ModuleType):
        "添加子模块。"
        func = getattr(module, "apply", None)

        if isinstance(func, types.FunctionType):
            inject_ok = self.check_sub_module_inject(module)
            if not inject_ok:
                raise SubModuleInjectError("子模块inject未满足。")
            return func(self)
        else:
            raise SubModuleNoExistApplyError("子模块未实现apply。")
        
    def check_sub_module_inject(self, module: types.ModuleType) -> bool:
        "检查子模块inject。"
        inject = getattr(module, "inject", None)
        if isinstance(inject, list):
            if all(k in self._handler for k in inject):
                return True
        else: 
            return True
        
        return False
    
__all__ = ['Event', 'Context']