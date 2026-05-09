import os
import sys

sys.path.insert(0, os.path.abspath("../.."))

project = 'Fitness Trainer'
copyright = '2026, Volodymyr Kyrylov'
author = 'Volodymyr Kyrylov'
release = '1.0'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

templates_path = ['_templates']
exclude_patterns = []

language = 'uk'

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'alabaster'
html_theme = "sphinx_rtd_theme"
html_static_path = ['_static']
