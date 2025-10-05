import asyncio
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from noishi import Context
import types

DEBOUNCE_DELAY = 1

class AutoReloadHandler(FileSystemEventHandler):
    def __init__(self, ctx: Context, modules: list[types.ModuleType], loop: asyncio.AbstractEventLoop):
        self.ctx = ctx
        self.modules = modules
        self.loop = loop
        self.paths_to_modules = {
            os.path.abspath(getattr(mod, "__file__", "")): mod
            for mod in modules
            if hasattr(mod, "__file__")
        }
        self._debounce_tasks = {}

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith(".py"):
            path = os.path.abspath(event.src_path)
            if path in self.paths_to_modules:
                mod = self.paths_to_modules[path]
                if mod.__name__ in self._debounce_tasks:
                    self._debounce_tasks[mod.__name__].cancel()
                
                self._debounce_tasks[mod.__name__] = asyncio.run_coroutine_threadsafe(
                    self._debounced_reload(mod), self.loop
                )

    async def _debounced_reload(self, mod: types.ModuleType):
        try:
            await asyncio.sleep(DEBOUNCE_DELAY)
            print(f"[watchdog] Detected change in {mod.__name__}, reloading...")
            await self.reload_module(mod.__name__)
        except asyncio.CancelledError:
            pass
        finally:
            self._debounce_tasks.pop(mod.__name__, None)
    
    async def reload_module(self, module_name: str):
        try:
            self.ctx.reload_sub_module(module_name)
            print(f"模块 {module_name} 重载成功")
        except Exception as e:
            print(f"模块重载失败:{e!r}")
            import traceback
            stack_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            print(stack_str)

async def auto_hot_reload(ctx: Context, modules: list[types.ModuleType], loop: asyncio.AbstractEventLoop):
    event_handler = AutoReloadHandler(ctx, modules, loop)
    observer = Observer()
    for mod in modules:
        mod_path = getattr(mod, "__file__", None)
        if mod_path:
            observer.schedule(event_handler, path=os.path.dirname(mod_path), recursive=False)
    observer.start()

    try:
        while True:
            await asyncio.sleep(1)
    finally:
        observer.stop()
        observer.join()