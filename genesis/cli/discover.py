import sys
import importlib
from typing import Union
from pathlib import Path

from rich import print
from rich.tree import Tree
from rich.panel import Panel
from rich.syntax import Syntax
from rich.padding import Padding

from genesis.logger import logger
from genesis.cli.exceptions import CLIExcpetion


def get_app_name(
    cls: object, module_import_str: str, app_name: Union[str, None] = None
) -> str:
    """Get the app name from the module."""
    try:
        mod = importlib.import_module(module_import_str)
    except (ImportError, ValueError):
        raise CLIExcpetion(
            "Ensure all the package directories have an [blue]__init__.py[/blue] file"
        )
    object_names = dir(mod)
    object_names_set = set(object_names)

    if app_name:
        if app_name not in object_names_set:
            raise CLIExcpetion(
                f"Could not find app name {app_name} in {module_import_str}"
            )

        app = getattr(mod, app_name)

        if not isinstance(app, cls):
            raise CLIExcpetion(
                f"The app name {app_name} in {module_import_str} doesn't seem to be a {cls.__name__} app"
            )

        return app_name

    for name in object_names:
        obj = getattr(mod, name)
        if isinstance(obj, cls):
            return name

    raise CLIExcpetion(f"Could not find {cls.__name__} app in module, try using --app")


def get_import_string(
    cls: object, path: Union[Path, None] = None, app_name: Union[str, None] = None
) -> str:
    """Get the import string for the given module path."""
    if not path:
        raise CLIExcpetion("A path to a Python file or package directory is required.")

    logger.info(f"Resolved absolute path {path.resolve()}")

    if not path.exists():
        raise CLIExcpetion(f"The path '{path}' does not exist.")

    absolute_path = path.resolve()
    module_path = absolute_path

    if absolute_path.is_file() and absolute_path.stem == "__init__":
        module_path = absolute_path.parent

    module_paths = [module_path]
    extra_sys_path = module_path.parent

    for parent in module_path.parents:
        init_path = parent / "__init__.py"

        if init_path.is_file():
            module_paths.insert(0, parent)
            extra_sys_path = parent.parent

        else:
            break

    root = module_paths[0]
    name = f"🐍 {root.name}" if root.is_file() else f"📁 {root.name}"

    tree = Tree(name)

    if root.is_dir():
        tree.add("[dim]🐍 __init__.py[/dim]")

    tree = tree

    for item in module_paths[1:]:
        name = f"🐍 {item.name}" if item.is_file() else f"📁 {item.name}"
        tree = tree.add(name)

        if item.is_dir():
            tree.add("[dim]🐍 __init__.py[/dim]")

    title = "[b green]Module file[/b green]"

    if len(module_paths) > 1 or module_path.is_dir():
        title = "[b green]Package file structure[/b green]"

    panel = Padding(
        Panel(
            tree,
            title=title,
            expand=False,
            padding=(1, 2),
        ),
        1,
    )
    print(panel)

    module_import_str = ".".join(p.stem for p in module_paths)

    logger.info(f"Importing module [green]{module_import_str}[/green]")

    extra_sys_path = extra_sys_path.resolve()

    sys.path.insert(0, str(extra_sys_path))

    use_app_name = get_app_name(cls, module_import_str, app_name=app_name)

    import_example = Syntax(f"from {module_import_str} import {use_app_name}", "python")

    import_panel = Padding(
        Panel(
            import_example,
            title=f"[b green]Importable {cls.__name__} app[/b green]",
            expand=False,
            padding=(1, 2),
        ),
        1,
    )

    logger.info(f"Found importable {cls.__name__} app")
    print(import_panel)

    import_string = f"{module_import_str}:{use_app_name}"
    logger.info(f"Using import string [b green]{import_string}[/b green]")

    return import_string
