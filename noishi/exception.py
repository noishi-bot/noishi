class InjectError(Exception):
    pass

class SubModuleError(Exception):
    pass

class SubModuleInjectError(SubModuleError,InjectError): 
    pass

class SubModuleNoExistApplyError(SubModuleError): 
    pass