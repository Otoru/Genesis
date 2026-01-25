import sys
import importlib
from typing import Union
from pathlib import Path

from genesis.logger import logger
from genesis.cli.exceptions import CLIExcpetion


def get_app_name(
    cls: type, module_import_str: str, app_name: Union[str, None] = None
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
    cls: type, path: Union[Path, None] = None, app_name: Union[str, None] = None
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

    logger.info(f"Module structure: {' -> '.join(p.name for p in module_paths)}")

    module_import_str = ".".join(p.stem for p in module_paths)

    logger.info(f"Importing module [green]{module_import_str}[/green]")

    extra_sys_path = extra_sys_path.resolve()

    sys.path.insert(0, str(extra_sys_path))

    use_app_name = get_app_name(cls, module_import_str, app_name=app_name)

    logger.info(f"Importable app: from {module_import_str} import {use_app_name}")

    import_string = f"{module_import_str}:{use_app_name}"
    logger.info(f"Using import string [b green]{import_string}[/b green]")

    return import_string
