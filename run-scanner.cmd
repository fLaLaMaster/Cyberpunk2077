@echo off
set "PYTHONPATH=%~dp0src"
python -m cp77compat scan --config "%~dp0cp77compat.yaml" %*
