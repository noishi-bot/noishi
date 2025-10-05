# Noishi
一个`Python`实现的依赖注入和事件框架。

## 状态
- 类型提示实现暂未完整,详情查看[类型提示](./res/type.md)  
- 本仓库就是`Demo`

## 食用
### 环境准备
- `CPython>=3.10`
- `PDM>=2.23`

### 下载源码

### 生成环境
```bash
pdm install
```

### 生成类型
```bash
pdm run gentype
```

### 运行`Demo`
```bash
pdm run main
```

## TODO:
- [x] `Context`基础实现
- [x] 事件管理
- [x] Demo
- [x] 模块热重载
- [ ] [类型提示](./res/type.md)