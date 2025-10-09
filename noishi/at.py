from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from noishi import Context

def _format_param(p) -> str:
    if p is None:
        return ""
    if isinstance(p, bool):
        return "1" if p else "0"
    if isinstance(p, (int, float)):
        return str(p)
    if isinstance(p, (list, tuple)):
        return ",".join(_format_param(x) for x in p)
    return str(p)


def at_command_build(
    command: str,
    *params,
    mode: str = "set",
    prefix: str = "AT",
    terminator: str = "\r\n",
) -> str:
    mode = mode.lower()
    if mode not in {"set", "read", "test", "exec"}:
        raise ValueError("mode must be one of 'set', 'read', 'test', 'exec'")

    cmd = f"{prefix}{command}"

    if mode == "read":
        cmd += "?"
    elif mode == "test":
        cmd += "=?"
    elif mode == "exec":
        pass
    elif mode == "set":
        if params:
            joined = ",".join(_format_param(p) for p in params)
            cmd += f"={joined}"
        else:
            cmd += "="

    if terminator:
        cmd += terminator

    return cmd

def at_command_expect(text: str, expected: str) -> list[str]:
    result = []
    lines = text.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line == "OK":
            break
        if line == "ERROR":
            raise RuntimeError("AT command error")
        if expected and line.startswith(expected):
            result.append(line[len(expected):].lstrip())
    return result

def apply(ctx: 'Context'):
    at = ctx.register("at")
    command = at.register("command")
    command.register("export",at_command_expect)
    command.register("build",at_command_build)
    return at

if __name__ == "__main__":
    print(at_command_build("+CMGD",1,0).encode())
    print(at_command_build("+CMGR",1).encode())