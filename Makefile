#############################################################################
# Makefile for building: gbi
#############################################################################
PREFIX?= /usr/local

####### Install

all:

install_doinstall:
	-sh install.sh $(PREFIX)

install: install_doinstall
