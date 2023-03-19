""" 插件加载测试

主要测试代码来自 https://github.com/Lancercmd/nonebot2-store-test
"""

import json
import re
import sys
from asyncio import create_subprocess_shell, run, subprocess
from pathlib import Path
from urllib.request import urlopen

# 匹配信息的正则表达式
ISSUE_PATTERN = r"\*\*{}：\*\*\s+([^\s*].*?)(?=(?:\s+\*\*|$))"
# 插件信息
PROJECT_LINK_PATTERN = re.compile(ISSUE_PATTERN.format("PyPI 项目名"))
MODULE_NAME_PATTERN = re.compile(ISSUE_PATTERN.format("插件 import 包名"))

RUNNER = """from nonebot import init, load_plugin, require

init(driver="~none")
valid = load_plugin("{}")
{}
if not valid:
    exit(1)
else:
    exit(0)
"""


ansi_escape = re.compile(
    r"""
    \x1B  # ESC
    (?:   # 7-bit C1 Fe (except CSI)
        [@-Z\\-_]
    |     # or [ for CSI, followed by a control sequence
        \[
        [0-?]*  # Parameter bytes
        [ -/]*  # Intermediate bytes
        [@-~]   # Final byte
    )
""",
    re.VERBOSE,
)


def get_plugin_list() -> dict[str, str]:
    """获取插件列表

    通过 package_name 获取 module_name
    """
    with urlopen("https://v2.nonebot.dev/plugins.json") as response:
        plugins = json.loads(response.read())

    return {plugin["project_link"]: plugin["module_name"] for plugin in plugins}


PLUGINS = get_plugin_list()


class PluginTest:
    def __init__(self, project_link: str, module_name: str) -> None:
        self._path = Path("plugin_test") / f"{project_link}-test"

        self.project_link = project_link
        self.module_name = module_name

        self._create = False
        self._run = False
        self._deps = []

        self._output_lines: list[str] = []

        self._plugin_list = PLUGINS

    async def run(self):
        await self.create_poetry_project()
        if self._create:
            await self.show_package_info()
            await self.show_plugin_dependencies()
            await self.run_poetry_project()

        output = "\n".join(self._output_lines)
        # 输出测试结果
        return self._run, ansi_escape.sub("", output)

    async def create_poetry_project(self) -> None:
        if not self._path.exists():
            proc = await create_subprocess_shell(
                f"poetry new {self._path.resolve()} && cd {self._path.resolve()} && poetry add {self.project_link} && poetry run python -m pip install -U pip {self.project_link}",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            code = proc.returncode

            self._create = not code
            if self._create:
                print(f"项目 {self.project_link} 创建成功。")
            else:
                self._log_output(f"项目 {self.project_link} 创建失败：")
                for i in stderr.decode().strip().splitlines():
                    self._log_output(f"    {i}")
        else:
            self._log_output(f"项目 {self.project_link} 已存在，跳过创建。")
            self._create = True

    async def show_package_info(self) -> None:
        if self._path.exists():
            proc = await create_subprocess_shell(
                f"cd {self._path.resolve()} && poetry show {self.project_link}",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            code = proc.returncode
            if not code:
                self._log_output(f"插件 {self.project_link} 的信息如下：")
                for i in stdout.decode().strip().splitlines():
                    self._log_output(f"    {i}")
            else:
                self._log_output(f"插件 {self.project_link} 信息获取失败。")

    async def show_plugin_dependencies(self) -> None:
        if self._path.exists():
            proc = await create_subprocess_shell(
                f"cd {self._path.resolve()} && poetry export --without-hashes",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            code = proc.returncode
            if not code:
                self._log_output(f"插件 {self.project_link} 依赖的插件如下：")
                for i in stdout.decode().strip().splitlines():
                    module_name = self._get_plugin_module_name(i)
                    if module_name:
                        self._deps.append(module_name)
                self._log_output(f"    {', '.join(self._deps)}")
            else:
                self._log_output(f"插件 {self.project_link} 依赖获取失败。")

    async def run_poetry_project(self) -> None:
        if self._path.exists():
            with open(self._path / "runner.py", "w") as f:
                f.write(
                    RUNNER.format(
                        self.module_name,
                        "\n".join([f"require('{i}')" for i in self._deps]),
                    )
                )

            proc = await create_subprocess_shell(
                f"cd {self._path.resolve()} && poetry run python runner.py",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            code = proc.returncode

            self._run = not code
            if self._run:
                self._log_output(f"插件 {self.module_name} 加载正常。")
            else:
                self._log_output(f"插件 {self.module_name} 加载出错：")
                _out = stdout.decode().strip().splitlines()
                _err = stderr.decode().strip().splitlines()
                for i in _out:
                    self._log_output(f"    {i}")
                for i in _err:
                    self._log_output(f"    {i}")

    def _log_output(self, output: str) -> None:
        """记录输出，同时打印到控制台"""
        print(output)
        self._output_lines.append(output)

    def _get_plugin_module_name(self, require: str) -> str | None:
        # anyio==3.6.2 ; python_version >= "3.11" and python_version < "4.0"
        # pydantic[dotenv]==1.10.6 ; python_version >= "3.10" and python_version < "4.0"
        match = re.match(r"^(.+?)(?:\[.+\])?==", require.strip())
        if match:
            package_name = match.group(1)
            # 不用包括自己
            if package_name in self._plugin_list and package_name != self.project_link:
                return self._plugin_list[package_name]


async def main():
    argv = sys.argv
    start = int(argv[1])
    length = int(argv[2])
    # 测试插件
    test_results = {}
    for i, (project_link, module_name) in enumerate(list(PLUGINS.items())[start:]):
        if i >= length:
            break
        test = PluginTest(project_link, module_name)
        result, output = await test.run()
        test_results[project_link] = result
        with open(test._path / "output.log", "w", encoding="utf8") as f:
            f.write(output)
        with open("results.json", "w", encoding="utf8") as f:
            json.dump(test_results, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    run(main())