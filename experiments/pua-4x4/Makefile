PYTHON ?= python3
BUILD_DIR ?= build

.PHONY: all verify install linux-verify pdf pdf-verify mapping-draft mapping-draft-verify complete-pdf complete-pdf-verify evidence-pdf evidence-pdf-verify math-proof v04-exact v04-exact-verify v04-hint-diagnostic v04-candidate3 v04-candidate3-verify v04-evidence-pdf v04-evidence-pdf-verify v05-candidate4 v05-candidate4-verify v06-candidate6 clean

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

math-proof:
	$(PYTHON) verify_mathematical_mapping.py

v04-exact: math-proof
	$(PYTHON) generate_pua4x4_v04_candidate.py

v04-exact-verify: v04-exact
	$(PYTHON) verify_pua4x4_v04_candidate.py
	$(PYTHON) audit_horizontal_placement.py
	$(PYTHON) verify_candidate_freetype_raster.py

v04-hint-diagnostic: v04-exact-verify
	$(PYTHON) make_v04_candidate2_hinted.py
	$(PYTHON) verify_v04_candidate2_derivation.py

v04-candidate3: v04-exact-verify
	$(PYTHON) make_v04_candidate3_seamguard.py

v04-candidate3-verify: v04-candidate3
	$(PYTHON) verify_v04_candidate3_derivation.py
	$(PYTHON) verify_v04_rc1_package.py

v04-evidence-pdf:
	$(PYTHON) generate_font_generation_evidence_pdf.py

v04-evidence-pdf-verify: v04-evidence-pdf
	$(PYTHON) verify_font_generation_evidence_pdf.py

v05-candidate4: v04-exact-verify
	$(PYTHON) make_v05_candidate4_strict.py

v05-candidate4-verify: v05-candidate4
	$(PYTHON) audit_candidate4_release.py

v06-candidate6:
	$(PYTHON) make_v06_candidate6_vertical_guard.py

clean:
	rm -rf -- $(BUILD_DIR)
