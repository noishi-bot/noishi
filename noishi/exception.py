class InjectError(Exception):
    """依赖注入相关异常的基类"""
    pass

class SubModuleError(Exception):
    """子模块相关异常的基类"""
    pass

class SubModuleInjectError(SubModuleError,InjectError): 
    """子模块依赖注入失败异常"""
    pass

class SubModuleNoExistApplyError(SubModuleError): 
    """子模块缺少apply函数异常"""
    pass

class SubModuleApplyArgsError(SubModuleError): 
    """子模块apply函数参数错误异常"""
    pass