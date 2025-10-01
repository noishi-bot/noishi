# 类型提示

![截图1](./screenshot1.png)

## 实现原理
使用`ast`静态分析调用`Context.register()`过的代码,生成类型信息  
![截图2](./screenshot2.png)  
具体实现可以参考[这个文件](../tool/type_export.py)

## TODO:
- [x] 项目内静态分析
- [ ] 任意依赖静态分析