# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# add project root to sys.path for autodoc
import os
import sys

sys.path.insert(0, os.path.abspath('../..'))
# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = '@PROJECT_NAME@'
copyright = '@CURRENT_YEAR@, Gergely Wootsch'
author = 'Gergely Wootsch'
release = '@App_VERSION@'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.coverage',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.autosectionlabel',
    'sphinx.ext.githubpages',
    'sphinx_markdown_builder'
]

napoleon_google_docstring = True
napoleon_use_param = False
napoleon_use_ivar = False

pygments_style = "vs"
pygments_dark_style = "stata-dark"

templates_path = ['_templates']
exclude_patterns = []

autodoc_default_options = {
    'autosummary': True,
    'member-order': 'groupwise',
    'show-inheritance': True,
    'preserve_defaults': True,
}
autodoc_preserve_defaults = True

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
html_theme_options = {
    "light_css_variables": {
        "color-brand-primary": "rgba(75, 180, 135, 1)",
        "color-brand-content": "rgba(75, 180, 135, 1)",
        "color-api-name": "rgba(0, 0, 0, 0.9)",
        "color-api-pre-name": "rgba(75, 180, 135, 0.75)",
        "color-highlight-on-target": "rgba(0,0,0,0)",
        "api-font-size": "var(--font-size--normal)",
    },
    "dark_css_variables": {
        "color-brand-primary": "rgba(90, 200, 155, 1)",
        "color-brand-content": "rgba(90, 200, 155, 1)",
        "color-highlight-on-target": "rgba(0,0,0,0)",
        "color-api-name": "rgba(255, 255, 255, 0.9)",
    },
    "navigation_with_keys": True,
}
highlight_language = "python"

html_static_path = ['_static']

# -- Favicon and logo -------------------------------------------------------
html_favicon = '../rsc/icon/icon.ico'
html_logo = '../rsc/icon/icon.png'

html_baseurl = 'https://github.com/wgergely/ExpenseTracker'
html_context = {
    "display_github": True,
    "github_user": "wgergely",
    "github_repo": "ExpenseTracker",
    "github_version": "main",
    "conf_py_path": "/docs/source",
}
