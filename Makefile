.PHONY: install run fmt lint

install:
\tpython -m pip install -U pip
\tpip install -r requirements.txt

run:
\tuvicorn api.service:app --reload --port 8080

fmt:
\tpython -m pip install black isort
\tblack .
\tisort .

lint:
\tpython -m pip install ruff
\truff check .