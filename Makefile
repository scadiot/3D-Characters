PYTHON := ".venv/Scripts/python.exe"

.PHONY: run test install models

# Lance le viewer
run:
	$(PYTHON) -m viewer.main

test:
	$(PYTHON) -m pytest

install:
	python -m venv .venv
	$(PYTHON) -m pip install -e .[dev]

# Régénère les personnages low poly de sample/Characters
models:
	$(PYTHON) tools/build_human.py
	$(PYTHON) tools/build_child.py
	$(PYTHON) tools/build_robot.py
	$(PYTHON) tools/build_star.py
	$(PYTHON) tools/build_talk.py
