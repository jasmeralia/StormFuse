VENV     := .venv

ifeq ($(OS),Windows_NT)
PYTHON   := python
VENV_BIN := $(VENV)/Scripts
PY       := $(VENV_BIN)/python.exe
else
PYTHON   := python3.12
VENV_BIN := $(VENV)/bin
PY       := $(VENV_BIN)/python
endif

PIP      := $(PY) -m pip

FFMPEG_SHA256_FILE := build/ffmpeg.sha256
FFMPEG_DIR         := resources/ffmpeg

.PHONY: venv deps fetch-ffmpeg generate-third-party run lint lintfix format test test-functional test-all installer clean

venv:
	@command -v $(PYTHON) >/dev/null 2>&1 || \
		{ echo "ERROR: $(PYTHON) not found. Install Python 3.12."; exit 1; }
	$(PYTHON) -m venv $(VENV)
	@echo "Virtualenv created at $(VENV). Run 'make deps' next."

deps: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt
	$(PIP) install --no-build-isolation -e .

fetch-ffmpeg:
	@echo "Downloading pinned ffmpeg build..."
	$(PY) build/fetch_ffmpeg.py

generate-third-party:
	$(PY) build/generate_third_party.py

run: deps
	$(PY) -m stormfuse

lint:
	$(PY) -m ruff check src/ tests/
	$(PY) -m mypy src/stormfuse/
	$(PY) -m pylint src/stormfuse/ --rcfile=.pylintrc

lintfix:
	$(PY) -m ruff format src/ tests/
	$(PY) -m ruff check --fix src/ tests/

format:
	$(PY) -m ruff format src/ tests/
	$(PY) -m ruff check --fix src/ tests/

test:
	$(PY) -m pytest tests/unit/ -v --cov=stormfuse --cov-report=xml

test-functional:
	$(PY) -m pytest tests/functional/ -v

test-all:
	$(PY) -m pytest tests/ -v --cov=stormfuse --cov-report=xml

installer:
	@echo "Building installer (Windows only)..."
	$(PY) build/generate_third_party.py
	$(PY) -m PyInstaller build/stormfuse.spec --noconfirm
	makensis build/installer/stormfuse.nsi

clean:
	rm -rf dist/ .pytest_cache/ .venv/ .mypy_cache/ .ruff_cache/ coverage.xml
	@if [ -d build ]; then \
		find build -mindepth 1 -maxdepth 1 \
			! -name installer \
			! -name fetch_ffmpeg.py \
			! -name generate_third_party.py \
			! -name ffmpeg.sha256 \
			! -name stormfuse.spec \
			-exec rm -rf {} +; \
	fi
	@if [ -d build/installer ]; then \
		find build/installer -mindepth 1 -maxdepth 1 \
			! -name stormfuse.nsi \
			-exec rm -rf {} +; \
	fi
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete
