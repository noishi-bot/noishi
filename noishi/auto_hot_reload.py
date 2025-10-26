import os
import traceback
import types
import watchfiles
from typing import Iterable, TypedDict
from pathlib import Path
from noishi import Context

class ModuleInfo(TypedDict):
    name: str
    path: Path

def get_module_info(mod: types.ModuleType) -> ModuleInfo:
    if hasattr(mod, "__path__") and mod.__path__:
        mod_path = mod.__path__[0] # dir_path
    elif hasattr(mod, "__file__") and mod.__file__:
        mod_path = mod.__file__ # file_path
    else:
        raise TypeError(f"Module {mod.__name__} is not watchable, skipping.")
    
    return ModuleInfo(
        name=mod.__name__,
        path=Path(os.path.abspath(mod_path))
    )

async def auto_hot_reload(
    ctx: Context, 
    module_infos: Iterable[types.ModuleType | ModuleInfo],
    debounce_delay_seconds: float = 1.0
):
    processed_module_infos = []
    for mod in module_infos:
        if isinstance(mod, types.ModuleType):
            processed_module_infos.append(get_module_info(mod))
        else:
            processed_module_infos.append(mod)
    module_infos = processed_module_infos

    if not module_infos:
        print("Auto hot-reload enabled, but no valid modules to watch.")
        return
    
    path_to_module = {mod_info["path"]: mod_info for mod_info in module_infos}
    watch_paths = list(path_to_module.keys())
    
    debounce_ms = int(debounce_delay_seconds * 1000)
    print(f"Starting hot-reload watcher on {len(watch_paths)} locations...")
    
    async for changes in watchfiles.awatch(
        *watch_paths,
        debounce=debounce_ms,
        watch_filter=watchfiles.PythonFilter()
    ):
        for change_type, file_path in changes:
            if change_type == watchfiles.Change.modified:
                file_path = Path(file_path).resolve()
                for watch_path in watch_paths:
                    watch_path = Path(watch_path).resolve()
                    if watch_path in file_path.parents or file_path == watch_path:
                        name = path_to_module[watch_path]["name"]
                        print(f"[watchfiles] Detected change in {name}, reloading...")
                        try:
                            ctx.reload_sub_module(name)
                            print(f"模块 {name} 重载成功")
                        except Exception as e:
                            stack_str = ''.join(traceback.format_exception(
                                type(e), e, e.__traceback__
                            ))
                            print(f"模块 {name} 重载失败:\n{stack_str}")
                        break
        