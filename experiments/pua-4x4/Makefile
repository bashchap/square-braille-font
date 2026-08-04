PYTHON ?= python3
BUILD_DIR ?= build

.PHONY: all verify install linux-verify pdf pdf-verify mapping-draft mapping-draft-verify complete-pdf complete-pdf-verify evidence-pdf evidence-pdf-verify clean

all:
	$(PYTHON) generate_pua4x4.py --output-dir $(BUILD_DIR)

verify: all
	$(PYTHON) verify_pua4x4.py $(BUILD_DIR)
	$(PYTHON) verify_equal_pixel_geometry.py $(BUILD_DIR)
	$(PYTHON) verify_trail_steps.py
	$(PYTHON) verify_demo_geometry.py
	$(PYTHON) demos4x4/verify_demos4x4.py
	$(PYTHON) verify_vortex_motion.py
	$(PYTHON) pua4x4_reference_renderer.py --columns 20 --rows 8 --seconds 0.05 --fps 20 >/dev/null
	$(PYTHON) pua4x4_motion_demo.py --columns 40 --rows 12 --seconds 0.05 --fps 20 --no-color >/dev/null

install: verify
	./install-linux-user.sh

linux-verify: install
	$(PYTHON) verify_linux_runtime.py
	$(PYTHON) verify_pango_seams.py

pdf:
	$(PYTHON) generate_spec_pdf.py

pdf-verify: pdf
	$(PYTHON) verify_spec_pdf.py

mapping-draft:
	$(PYTHON) generate_mapping_spec_draft_pdf.py

mapping-draft-verify: mapping-draft
	$(PYTHON) verify_mapping_spec_draft_pdf.py

complete-pdf: mapping-draft pdf
	$(PYTHON) assemble_complete_spec_pdf.py

complete-pdf-verify: complete-pdf
	$(PYTHON) verify_mapping_spec_draft_pdf.py
	$(PYTHON) verify_spec_pdf.py
	$(PYTHON) verify_complete_spec_pdf.py

evidence-pdf:
	$(PYTHON) generate_mapping_chain_evidence_pdf.py

evidence-pdf-verify: evidence-pdf
	$(PYTHON) verify_mapping_chain_evidence_pdf.py

clean:
	rm -rf -- $(BUILD_DIR)
