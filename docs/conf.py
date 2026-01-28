# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import importlib.metadata
import inspect
import os
from importlib import import_module


from typing import Any

project = 'rocrate-action-recorder'
version = release = importlib.metadata.version("rocrate-action-recorder")

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.mathjax",
    "sphinx.ext.napoleon",
    "sphinx.ext.linkcode",
    "autoapi.extension",
    "sphinx_autodoc_typehints",
    "sphinx_copybutton",
]

source_suffix = [".rst", ".md"]
exclude_patterns = [
    "_build",
    "**.ipynb_checkpoints",
    "Thumbs.db",
    ".DS_Store",
    ".env",
    ".venv",
]

html_theme = "furo"

html_theme_options: dict[str, Any] = {
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/i-VRESSE/rocrate-action-recorder",
            "html": """
                <svg stroke="currentColor" fill="currentColor" stroke-width="0" viewBox="0 0 16 16">
                    <path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"></path>
                </svg>
            """,
            "class": "",
        },
    ],
    "source_repository": "https://github.com/i-VRESSE/rocrate-action-recorder",
    "source_branch": "main",
    "source_directory": "docs/",
}

myst_enable_extensions = [
    "colon_fence",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# TODO what is this?
nitpick_ignore = [
    ("py:class", "_io.StringIO"),
    ("py:class", "_io.BytesIO"),
]

always_document_param_types = True

autoapi_dirs = ['../src/rocrate_action_recorder']


# Link to source on GitHub for objects documented by Sphinx's linkcode extension.
# Implements the contract described at:
# https://www.sphinx-doc.org/en/master/usage/extensions/linkcode.html
def linkcode_resolve(domain: str, info: dict) -> str | None:
    """Return a GitHub URL to the source for the given object.

    The function resolves Python objects (domain == "py") by importing the
    module and walking the attribute path. It then uses :mod:`inspect` to find
    the source file and line numbers and constructs a URL of the form:

    {repo}/blob/{branch}/{path}#L{start}-L{end}
    """
    if domain != "py":
        return None

    module_name = info.get("module")
    fullname = info.get("fullname")
    if not module_name:
        return None

    try:
        module = import_module(module_name)
        obj = module
        if fullname:
            for part in fullname.split("."):
                obj = getattr(obj, part)

        # Get source file and line numbers
        filename = inspect.getsourcefile(obj) or inspect.getfile(obj)
        if not filename:
            return None
        source_lines, start_line = inspect.getsourcelines(obj)
    except Exception:
        return None

    # Hardcoded repository and branch for link targets
    repo = "https://github.com/i-VRESSE/rocrate-action-recorder".rstrip("/")
    branch = "main"

    filename = os.path.normpath(filename)
    parts = filename.split(os.path.sep)

    # Prefer path rooted at the package name; GitHub layout uses `src/rocrate_action_recorder/...`
    relpath: str | None = None
    try:
        idx = parts.index("rocrate_action_recorder")
        relpath = os.path.join("src", *parts[idx:])
    except ValueError:
        if "src" in parts:
            idx = parts.index("src")
            relpath = os.path.join(*parts[idx:])

    if relpath is None:
        return None

    end_line = start_line + len(source_lines) - 1
    return f"{repo}/blob/{branch}/{relpath}#L{start_line}-L{end_line}"
