# 类型提示

![截图1](./screenshot1.png)

## 实现原理
使用`ast`静态分析调用`Context.register()`过的代码,生成类型信息  
例如生成:  
```python
"""Auto-generated types"""
from typing import Any, Awaitable, Callable, List, Optional, Protocol, Union
from noishi.ctx import Context

class DepProtocol_Noishi_Logger_Logger(Protocol):

    def __init__(self, ctx: Context, name: str='root'):
        ...

    async def _log(self, level: str, message: str):
        ...

    async def debug(self, message: str):
        ...

    async def info(self, message: str):
        ...

    async def warning(self, message: str):
        ...

    async def error(self, message: str):
        ...

class ExtendContext_Noishi_Main(Protocol):
    """Auto-generated Extend protocol for noishi.main.ctx"""

    def logger(self, name: str='root') -> DepProtocol_Noishi_Logger_Logger:
        ...
    pdu: 'ExtendContext_Noishi_Pdu_Ctx_Pdu'

class ExtendContext_Noishi_Pdu_Ctx_Pdu(Protocol):
    """Auto-generated Extend protocol for noishi.pdu.ctx.pdu"""

    async def decode(self, pdu: str) -> Awaitable[tuple[str, str, str]]:
        ...

class ExtendContext_Noishi_Pdu(Protocol):
    """Auto-generated Extend protocol for noishi.pdu with inject dependencies"""

    def logger(self, name: str='root') -> DepProtocol_Noishi_Logger_Logger:
        ...
``` 
具体实现可以参考[这个文件](../tool/type_export.py)  
由于`Python`是**动态类型**的语言,静态分析是**不可能完美**的,因此**bug很多**,实际生产应用请使用[`cordis`](https://cordis.io/)或用**静态类型**的其他语言实现。

## TODO:
- [x] 项目内静态分析
- [ ] 任意依赖静态分析
- [ ] 直接生成`*.pyi`文件