.PHONY: test tests

PYTHON ?= $(shell which python3)
DEST_DIR ?= $(shell echo ~/.local/usr/bin)

test: tests
tests:
	${PYTHON} -m unittest tests

install:
	mkdir -p ${DEST_DIR}
	cp -r ./localbkup.py ${DEST_DIR}/localbkup.py
	chmod +x ${DEST_DIR}/localbkup.py
