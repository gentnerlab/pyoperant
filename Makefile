# PyOperant Lab Manual — document build
# Source of truth is the Markdown; PDF/DOCX are generated artifacts.
MANUAL   := pyoperant_manual
SRC      := $(MANUAL).md
PDF      := $(MANUAL).pdf
DOCX     := $(MANUAL).docx
DEFAULTS := $(MANUAL).defaults.yaml
HEADER   := $(MANUAL).head.tex

.PHONY: pdf docx all clean
pdf: $(PDF)              ## build the styled PDF (default)
$(PDF): $(SRC) $(DEFAULTS) $(HEADER)
	pandoc $(SRC) -d $(DEFAULTS) -o $(PDF)

docx: $(SRC)             ## build a Word .docx
	pandoc $(SRC) -f gfm -o $(DOCX) -s --toc --toc-depth=3 \
	  --metadata title="PyOperant Lab Manual"

all: pdf docx

clean:                   ## remove generated artifacts
	rm -f $(PDF) $(DOCX)
