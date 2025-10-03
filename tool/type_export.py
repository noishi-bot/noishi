import ast
import re
import os
from typing import Optional, Union
from collections import defaultdict

class RegisterVisitor(ast.NodeVisitor):
    
    def __init__(self, module_prefix: str):
        self.module_prefix = module_prefix
        self.registers: dict[str, dict[str, dict]] = {}
        self.functions: dict[str, Union[ast.FunctionDef, ast.AsyncFunctionDef]] = {}
        self.classes: dict[str, ast.ClassDef] = {}
        self.var_ctx_map: dict[str, str] = {}
        self.imports: dict[str, str] = {}
        self.calls: list[tuple[str, Optional[str], list[str]]] = []
        self.local_contexts: set[str] = set()
        self.inject_list: Optional[list[str]] = None

    def visit_ClassDef(self, node: ast.ClassDef):
        key = f"{self.module_prefix}.{node.name}"
        self.classes[key] = node
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._register_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._register_function(node)
        self.generic_visit(node)

    def _register_function(self, node):
        key = f"{self.module_prefix}_{node.name}"
        self.functions[key] = node

    def visit_Call(self, node: ast.Call):
        if self._is_register_call(node):
            base, calls = self._extract_register_chain(node)
            if base and calls:
                if not base.startswith(self.module_prefix + '.') and base != self.module_prefix:
                    path = f"{self.module_prefix}.{base}"
                else:
                    path = base
                for call in calls:
                    name = self._get_register_name(call)
                    typ = self._get_register_type(call)
                    if not name:
                        break
                    if path not in self.registers:
                        self.registers[path] = {}
                    self.registers[path][name] = {'type': typ or 'ctx', 'node': call}
                    path = f"{path}.{name}"
            else:
                self._process_register_call(node)
        
        try:
            if not self._is_register_call(node):
                func = node.func
                func_base = None
                func_attr = None
                if isinstance(func, ast.Name):
                    func_base = func.id
                elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    func_base = func.value.id
                    func_attr = func.attr
                if func_base:
                    arg_names = [a.id for a in node.args if isinstance(a, ast.Name)]
                    if arg_names:
                        self.calls.append((func_base, func_attr, arg_names))
        except Exception:
            pass
        
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target_name = node.targets[0].id
            value = node.value
            if isinstance(value, ast.Call) and self._is_register_call(value):
                base, calls = self._extract_register_chain(value)
                if base and calls:
                    path = base
                    for c in calls:
                        rname = self._get_register_name(c)
                        if not rname:
                            break
                        path = f"{path}.{rname}"
                    if not path.startswith(self.module_prefix + '.') and path != self.module_prefix:
                        path = f"{self.module_prefix}.{path}"
                    self.var_ctx_map[target_name] = path
            elif isinstance(value, ast.Attribute):
                name = self._get_ctx_name(value)
                if name:
                    if not name.startswith(self.module_prefix + '.') and name != self.module_prefix:
                        name = f"{self.module_prefix}.{name}"
                    self.var_ctx_map[target_name] = name
            elif isinstance(value, ast.Call) and self._is_context_call(value):
                self.var_ctx_map[target_name] = f"{self.module_prefix}.ctx"
                self.local_contexts.add(f"{self.module_prefix}.ctx")
        
        if (len(node.targets) == 1 and 
            isinstance(node.targets[0], ast.Name) and 
            node.targets[0].id == 'inject' and
            isinstance(node.value, ast.List)):
            self.inject_list = []
            for element in node.value.elts:
                if isinstance(element, ast.Constant) and isinstance(element.value, str):
                    self.inject_list.append(element.value)
        
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ''
        for alias in node.names:
            name = alias.asname or alias.name
            if module:
                self.imports[name] = f"{module}.{alias.name}"
            else:
                self.imports[name] = alias.name

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.asname or alias.name
            self.imports[name] = alias.name

    def _is_register_call(self, node: ast.Call) -> bool:
        return (isinstance(node.func, ast.Attribute)
                and node.func.attr == 'register')

    def _process_register_call(self, node: ast.Call):
        ctx_name = self._get_ctx_name(node.func.value)
        if not ctx_name:
            return
        reg_name = self._get_register_name(node)
        type_str = self._get_register_type(node)
        
        if not ctx_name.startswith(self.module_prefix + '.') and ctx_name != self.module_prefix:
            ctx_name = f"{self.module_prefix}.{ctx_name}"
        if ctx_name not in self.registers:
            self.registers[ctx_name] = {}
        
        self.registers[ctx_name][reg_name] = {
            'type': type_str,
            'node': node
        }

    def _get_register_name(self, node: ast.Call) -> Optional[str]:
        if node.args and isinstance(node.args[0], ast.Constant):
            return node.args[0].value
        return None

    def _get_register_type(self, node: ast.Call) -> Optional[str]:
        if len(node.args) == 1:
            return 'ctx'
        
        if len(node.args) > 1:
            return self._analyze_register_type(node.args[1])
        
        return None

    def _analyze_register_type(self, arg_node) -> Optional[str]:
        if isinstance(arg_node, ast.Call) and self._is_context_call(arg_node):
            return 'ctx'
        elif isinstance(arg_node, ast.Name):
            return f"{self.module_prefix}_{arg_node.id}"
        elif isinstance(arg_node, ast.Lambda):
            return '<lambda>'
        elif isinstance(arg_node, ast.Call):
            class_name = ast.unparse(arg_node.func).strip()
            full_key = f"{self.module_prefix}.{class_name}"
            if full_key in self.classes:
                return full_key
            return class_name
        return None

    def _is_context_call(self, node: ast.Call) -> bool:
        return (isinstance(node.func, ast.Name)
                and node.func.id == 'Context')

    def _get_ctx_name(self, node) -> Optional[str]:
        if isinstance(node, ast.Name):
            return self.var_ctx_map.get(node.id, node.id)
        elif isinstance(node, ast.Attribute):
            parent = self._get_ctx_name(node.value)
            if parent:
                return f"{parent}.{node.attr}"
            return node.attr
        return None

    def _extract_register_chain(self, node: ast.Call):
        calls = []
        cur = node
        while isinstance(cur, ast.Call) and self._is_register_call(cur):
            calls.insert(0, cur)
            func = cur.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Call):
                cur = func.value
                continue
            else:
                if isinstance(func, ast.Attribute):
                    base = self._get_ctx_name(func.value)
                    return base, calls
                break
        return None, calls

class TypeGenerator:
    def __init__(self, all_regs: dict, all_funcs: dict, all_classes: dict, ctx_path: str, ctx_import_path: str, local_contexts: set, all_mounts: dict, all_injects: dict):
        self.all_regs = all_regs
        self.all_funcs = all_funcs
        self.all_classes = all_classes
        self.ctx_path = ctx_path
        self.ctx_import_path = ctx_import_path
        self.local_contexts = local_contexts
        self.all_mounts = all_mounts
        self.all_injects = all_injects
        self.dependency_classes = set()

    def generate_module(self) -> ast.Module:
        self._collect_all_dependencies()
        
        module = ast.Module(body=[], type_ignores=[])
        module.body.extend(self._create_module_header())
        module.body.extend(self._create_dependency_protocols())
        module.body.extend(self._create_extend_protocols())
        module.body.extend(self._create_inject_protocols())
        ast.fix_missing_locations(module)
        return module

    def _collect_all_dependencies(self):
        registered_types = set()
        for regs in self.all_regs.values():
            for info in regs.values():
                typ = info.get('type')
                if typ and isinstance(typ, str) and typ != 'ctx' and not typ.startswith('<'):
                    registered_types.add(typ)

        for typ in registered_types:
            if typ in self.all_funcs:
                fn_node = self.all_funcs[typ]
                if fn_node.returns:
                    self._collect_dependencies_from_node(fn_node.returns)
            
            if typ in self.all_classes:
                self.dependency_classes.add(typ)
            else:
                class_key = next((k for k in self.all_classes if k.endswith('.' + typ)), None)
                if class_key:
                    self.dependency_classes.add(class_key)

    def _pascalize(self, name: str) -> str:
        if not name:
            return ""
        parts = [p for p in re.split(r"[^0-9a-zA-Z]+", name) if p]
        if not parts:
            return name[0].upper() + name[1:] if name else ""
        return ''.join(p[0].upper() + p[1:] for p in parts)
    
    def _path_to_protocol_name(self, path: str, prefix: str) -> str:
        if not path:
            return prefix
        clean_path = re.sub(r'\.(py|ctx)$', '', path)
        pascal_parts = [self._pascalize(p) for p in clean_path.split('.')]
        return f"{prefix}_" + "_".join(pascal_parts)

    def _get_class_protocol_name(self, class_key: str) -> str:
        module_path, class_name = class_key.rsplit('.', 1)
        return self._path_to_protocol_name(f"{module_path}.{class_name}", prefix="DepProtocol")
    
    def _get_context_protocol_name(self, ctx_path: str) -> str:
        return self._path_to_protocol_name(ctx_path, prefix="ExtendContext")

    def _collect_dependencies_from_node(self, node):
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id in [cls.split('.')[-1] for cls in self.all_classes]:
                full_key = next((k for k in self.all_classes if k.endswith('.' + child.id)), None)
                if full_key:
                    self.dependency_classes.add(full_key)

    def _create_protocol_method_from_function(self, stmt: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> Union[ast.FunctionDef, ast.AsyncFunctionDef]:
        body = [ast.Expr(value=ast.Constant(value=Ellipsis))]
        
        if isinstance(stmt, ast.FunctionDef):
            return ast.FunctionDef(
                name=stmt.name,
                args=stmt.args,
                body=body,
                decorator_list=stmt.decorator_list,
                returns=stmt.returns
            )
        else:
            return ast.AsyncFunctionDef(
                name=stmt.name,
                args=stmt.args,
                body=body,
                decorator_list=stmt.decorator_list,
                returns=stmt.returns
            )
            
    def _create_dependency_protocols(self) -> list:
        protocols = []
        created = set()
        for class_key in sorted(self.dependency_classes):
            if class_key not in self.all_classes:
                continue
            class_node = self.all_classes[class_key]
            proto_name = self._get_class_protocol_name(class_key)
            
            if proto_name in created:
                continue
            created.add(proto_name)
            
            proto_body = []
            for stmt in class_node.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    proto_method = self._create_protocol_method_from_function(stmt)
                    proto_body.append(proto_method)
                elif isinstance(stmt, ast.AnnAssign):
                    proto_body.append(stmt)
            
            if not proto_body:
                proto_body = [ast.Expr(value=ast.Constant(value=Ellipsis))]
                
            protocols.append(ast.ClassDef(
                name=proto_name,
                bases=[ast.Name(id='Protocol', ctx=ast.Load())],
                keywords=class_node.keywords,
                body=proto_body,
                decorator_list=[]
            ))
        return protocols

    def _create_extend_protocols(self) -> list:
        classes = []
        created = set()
        
        abstract_contexts = {path for paths in self.all_mounts.values() for path in paths}
        protocol_targets = set()
        protocol_targets.update(self.local_contexts)
        
        for ctx_path, regs in self.all_regs.items():
            if not self._is_external_context(ctx_path):
                protocol_targets.add(ctx_path)
            
            for reg_name, info in regs.items():
                if info.get('type') == 'ctx':
                    sub_ctx_path = f"{ctx_path}.{reg_name}"
                    protocol_targets.add(sub_ctx_path)
                    
        for ctx_path in sorted(list(protocol_targets)):
            if ctx_path in abstract_contexts and ctx_path not in self.local_contexts:
                continue
                
            proto_name = self._get_context_protocol_name(ctx_path)
            if proto_name in created:
                continue
            created.add(proto_name)
            
            class_body = [ast.Expr(value=ast.Constant(value=f'Auto-generated Extend protocol for {ctx_path}'))]
            
            if ctx_path in self.all_regs:
                for reg_name, info in self.all_regs[ctx_path].items():
                    member = self._create_registered_member(reg_name, info, ctx_path)
                    if member:
                        class_body.append(member)
            
            if ctx_path in self.all_mounts:
                for mounted_path in self.all_mounts[ctx_path]:
                    if mounted_path in self.all_regs:
                        for reg_name, info in self.all_regs[mounted_path].items():
                            member = self._create_registered_member(reg_name, info, mounted_path)
                            if member:
                                class_body.append(member)
            
            if len(class_body) > 1:
                classes.append(ast.ClassDef(
                    name=proto_name,
                    bases=[ast.Name(id='Protocol', ctx=ast.Load())],
                    keywords=[],
                    body=class_body,
                    decorator_list=[]
                ))
        
        referenced_protocols = set()
        for cls in classes:
            for node in ast.walk(cls):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("ExtendContext_"):
                    referenced_protocols.add(node.value)
        
        for ref_name in referenced_protocols:
            if ref_name not in created:
                created.add(ref_name)
                ctx_path = ref_name.replace("ExtendContext_", "").lower().replace("_", ".")
                
                classes.append(ast.ClassDef(
                    name=ref_name,
                    bases=[ast.Name(id='Protocol', ctx=ast.Load())],
                    keywords=[],
                    body=[ast.Expr(value=ast.Constant(value=f'Auto-generated Extend protocol for {ctx_path}'))],
                    decorator_list=[],
                ))
        return classes

    def _create_inject_protocols(self) -> list:
        classes = []
        
        for module_path, inject_list in self.all_injects.items():
            if not inject_list:
                continue
                
            proto_name = self._path_to_protocol_name(f"{module_path}.ctx", "ExtendContext")
            
            class_body = [ast.Expr(value=ast.Constant(value=f'Auto-generated Extend protocol for {module_path} with inject dependencies'))]
            
            for inject_name in inject_list:
                member = self._create_inject_member(inject_name, module_path)
                if member:
                    class_body.append(member)
            
            if len(class_body) > 1:
                classes.append(ast.ClassDef(
                    name=proto_name,
                    bases=[ast.Name(id='Protocol', ctx=ast.Load())],
                    keywords=[],
                    body=class_body,
                    decorator_list=[]
                ))
        
        return classes

    def _find_dependency_type(self, inject_name: str, module_path: str):
        ctx_path = f"{module_path}.ctx"
        if ctx_path in self.all_regs and inject_name in self.all_regs[ctx_path]:
            info = self.all_regs[ctx_path][inject_name]
            return self._create_registered_member(inject_name, info, ctx_path)
        
        for ctx_path, regs in self.all_regs.items():
            if inject_name in regs:
                info = regs[inject_name]
                return self._create_registered_member(inject_name, info, ctx_path)
        
        return self._create_fallback_annotation(inject_name)

    def _create_inject_member(self, name: str, module_path: str):
        member = self._find_dependency_type(name, module_path)
        return member

    def _is_external_context(self, ctx_path: str) -> bool:
        if ctx_path in self.local_contexts:
            return False
        
        parts = ctx_path.split('.')
        if len(parts) > 1:
            return True
            
        return False

    def _create_module_header(self) -> list:
        header = [ast.Expr(value=ast.Constant(value='Auto-generated types'))]
        header.extend(self._create_imports())
        return header

    def _create_imports(self) -> list[ast.ImportFrom]:
        typing_names = {
            'Protocol', 'Optional', 'Awaitable', 'Any',
            'Callable', 'Union'
        }
        
        imports = []
        
        imports.append(ast.ImportFrom(
            module='typing',
            names=[ast.alias(name=n, asname=None) for n in sorted(typing_names)],
            level=0
        ))

        imports.append(ast.ImportFrom(
            module=self.ctx_import_path,
            names=[ast.alias(name="Context", asname=None)],
            level=0
        ))
        
        return imports

    def _create_registered_member(self, reg_name: str, info: dict, parent_ctx: str):
        typ = info.get('type')
        
        if typ == 'ctx':
            return self._create_subcontext_annotation(reg_name, f"{parent_ctx}.{reg_name}")

        if typ in self.all_classes:
            return self._create_class_property(reg_name, typ)
        
        if typ in self.all_funcs:
            return self._create_function_method(reg_name, typ, parent_ctx)

        class_key = next((k for k in self.all_classes if k.endswith('.' + typ)), None)
        if class_key:
            return self._create_class_property(reg_name, class_key)

        return self._create_fallback_annotation(reg_name)

    def _create_class_property(self, name: str, class_key: str) -> ast.AnnAssign:
        protocol_name = self._get_class_protocol_name(class_key)
        return ast.AnnAssign(
            target=ast.Name(id=name, ctx=ast.Store()),
            annotation=ast.Name(id=protocol_name, ctx=ast.Load()),
            value=None,
            simple=1
        )

    def _create_subcontext_annotation(self, name: str, full_ctx_path: str) -> ast.AnnAssign:
        protocol_name = self._get_context_protocol_name(full_ctx_path)
        return ast.AnnAssign(
            target=ast.Name(id=name, ctx=ast.Store()),
            annotation=ast.Constant(value=protocol_name),
            value=None,
            simple=1
        )

    def _create_function_method(self, reg_name: str, func_key: str, ctx_path: str):
        fn_node = self.all_funcs[func_key]
        
        new_fn_node = fn_node 
        if fn_node.returns and isinstance(fn_node.returns, ast.Name):
            class_name = fn_node.returns.id
            class_key = next((k for k in self.all_classes if k.endswith('.' + class_name)), None)
            if class_key:
                new_returns = ast.Name(
                    id=self._get_class_protocol_name(class_key),
                    ctx=ast.Load()
                )
                
                if isinstance(fn_node, ast.FunctionDef):
                    new_fn_node = ast.FunctionDef(
                        name=fn_node.name, args=fn_node.args, body=fn_node.body,
                        decorator_list=fn_node.decorator_list, returns=new_returns
                    )
                else:
                    new_fn_node = ast.AsyncFunctionDef(
                        name=fn_node.name, args=fn_node.args, body=fn_node.body,
                        decorator_list=fn_node.decorator_list, returns=new_returns
                    )
                
        return self._convert_function_to_method(new_fn_node, reg_name)

    def _convert_function_to_method(self, fn_node: Union[ast.FunctionDef, ast.AsyncFunctionDef], method_name: str):
        new_args = self._build_method_args(fn_node.args)
        returns = self._build_method_returns(fn_node)
        body = [ast.Expr(value=ast.Constant(value=Ellipsis))]
        
        common_args = {
            'name': method_name,
            'args': new_args,
            'body': body,
            'decorator_list': [],
            'returns': returns
        }
        
        if isinstance(fn_node, ast.AsyncFunctionDef):
            return ast.AsyncFunctionDef(**common_args)
        else:
            return ast.FunctionDef(**common_args)

    def _build_method_args(self, original_args: ast.arguments) -> ast.arguments:
        new_args_list = [ast.arg(arg='self')]
        
        original_args_list = original_args.args
        if original_args_list and original_args_list[0].arg == 'self':
            original_args_list = original_args_list[1:]
            
        for arg in original_args_list:
            new_args_list.append(ast.arg(arg=arg.arg, annotation=arg.annotation))
        
        return ast.arguments(
            posonlyargs=[],
            args=new_args_list,
            vararg=original_args.vararg,
            kwonlyargs=original_args.kwonlyargs,
            kw_defaults=original_args.kw_defaults,
            defaults=original_args.defaults
        )

    def _build_method_returns(self, fn_node: Union[ast.FunctionDef, ast.AsyncFunctionDef]):
        returns = fn_node.returns or ast.Name(id='Any', ctx=ast.Load())
        
        if isinstance(fn_node, ast.AsyncFunctionDef):
            returns = ast.Subscript(
                value=ast.Name(id='Awaitable', ctx=ast.Load()),
                slice=returns,
                ctx=ast.Load()
            )
        
        return returns

    def _create_fallback_annotation(self, name: str) -> ast.AnnAssign:
        default_callable = ast.parse(
            'Callable[..., Awaitable[Any]]',
            mode='eval'
        ).body
        
        opt_ann = ast.Subscript(
            value=ast.Name(id='Optional', ctx=ast.Load()),
            slice=default_callable,
            ctx=ast.Load()
        )
        
        return ast.AnnAssign(
            target=ast.Name(id=name, ctx=ast.Store()),
            annotation=opt_ann,
            value=ast.Constant(value=None),
            simple=1
        )

def _get_module_prefix(file_path: str) -> str:
    rel_path = os.path.relpath(file_path)
    rel_no_ext = os.path.splitext(rel_path)[0]
    parts = [p for p in rel_no_ext.split(os.sep) if p]
    return '.'.join(parts)

def scan_directory(src_dir: str) -> tuple[dict, dict, dict, set, dict, dict]:
    all_funcs = {}
    all_classes = {}
    all_local_contexts = set()
    visitors = {}
    all_injects = {}
    
    for root, _, files in os.walk(src_dir):
        for filename in files:
            if filename.endswith('.py'):
                file_path = os.path.join(root, filename)
                mod_name = _get_module_prefix(file_path)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        src = f.read()
                    tree = ast.parse(src, filename=file_path)
                    
                    visitor = RegisterVisitor(mod_name)
                    visitor.visit(tree)
                    visitors[mod_name] = visitor
                    all_funcs.update(visitor.functions)
                    all_classes.update(visitor.classes)
                    all_local_contexts.update(visitor.local_contexts)
                    
                    if visitor.inject_list is not None:
                        all_injects[mod_name] = visitor.inject_list
                        
                except Exception as e:
                    print(f"Error scanning file {file_path}: {e}")
    
    all_mounts = defaultdict(list)
    for mod_name, visitor in visitors.items():
        for func_base, func_attr, arg_names in visitor.calls:
            if not arg_names:
                continue
            caller_ctx_path = None
            callee_module_name = None
            func_name = func_attr or func_base
            if 'apply' in func_name.lower():
                ctx_arg_name = arg_names[0]
                caller_ctx_path = visitor.var_ctx_map.get(ctx_arg_name)
                
                if func_attr:
                    callee_module_name = func_base
                else:
                    raw_import = visitor.imports.get(func_base)
                    if raw_import:
                        callee_module_name = ".".join(raw_import.split('.')[:-1])
            
            elif func_attr and 'add_sub_module' in func_attr.lower():
                caller_ctx_path = visitor.var_ctx_map.get(func_base)
                callee_module_name = arg_names[0]
                
            if caller_ctx_path and callee_module_name:
                callee_module_path = visitor.imports.get(callee_module_name, callee_module_name)
                
                abstract_ctx_path = f"{callee_module_path}.ctx"
                if abstract_ctx_path not in all_mounts[caller_ctx_path]:
                    all_mounts[caller_ctx_path].append(abstract_ctx_path)
            
    all_regs = {}
    for visitor in visitors.values():
        for ctx_name, reg_info in visitor.registers.items():
            if ctx_name not in all_regs:
                all_regs[ctx_name] = {}
            all_regs[ctx_name].update(reg_info)
    
    return all_regs, all_funcs, all_classes, all_local_contexts, all_mounts, all_injects

def save_generated_types(all_regs: dict, all_funcs: dict, all_classes: dict, local_contexts: set, all_mounts: dict, all_injects: dict, save_path: str, ctx_path:str, ctx_import_path: str):
    generator = TypeGenerator(all_regs, all_funcs, all_classes, ctx_path, ctx_import_path, local_contexts, all_mounts, all_injects)
    module_ast = generator.generate_module()
    
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write(ast.unparse(module_ast))
    
    print(f"Saved context types -> {save_path}")

def main():
    registrations, functions, classes, local_ctxs, mounts, injects = scan_directory("./noishi")
    save_generated_types(registrations, functions, classes, local_ctxs, mounts, injects, "./noishi/etype/ctx.py", "./noishi/ctx.py", "noishi.ctx")