PYTHON ?= python3
FONTFORGE ?= fontforge
DEJAVU_MONO ?= /usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf
BUILD_DIR ?= build

CURRENT_NAME = Square-Braille-Unicode-Text-Seamless
TEXT_NAME = PUA-Square-Braille-Text-Seamless
GRAPHICS_NAME = PUA-Square-Braille-Seamless

.PHONY: all verify mac-test-100 verify-mac-test-100 clean

all: $(BUILD_DIR)/$(CURRENT_NAME).ttf $(BUILD_DIR)/$(CURRENT_NAME).otf

$(BUILD_DIR)/$(GRAPHICS_NAME).ttf:
	mkdir -p $(BUILD_DIR)
	$(FONTFORGE) -lang=py -script src/font/generate_font.py \
		--font-name "PUA Square Braille Seamless" --version 1.4 \
		--edge-overfill 100 --output-dir $(BUILD_DIR)

$(BUILD_DIR)/$(TEXT_NAME).ttf: $(BUILD_DIR)/$(GRAPHICS_NAME).ttf
	test -f "$(DEJAVU_MONO)"
	$(FONTFORGE) -lang=py -script src/font/add_text_to_font.py \
		--graphics-font $< --text-font "$(DEJAVU_MONO)" \
		--font-name "PUA Square Braille Text Seamless" --version 1.4 \
		--output-dir $(BUILD_DIR)

$(BUILD_DIR)/$(CURRENT_NAME).ttf: $(BUILD_DIR)/$(TEXT_NAME).ttf
	$(PYTHON) src/font/map_unicode_braille.py $< $@ --version 1.4

$(BUILD_DIR)/$(CURRENT_NAME).otf: $(BUILD_DIR)/$(TEXT_NAME).ttf
	$(PYTHON) src/font/map_unicode_braille.py \
		$(BUILD_DIR)/$(TEXT_NAME).otf $@ --version 1.4

verify: all
	$(PYTHON) src/font/verify_unicode_braille.py \
		$(BUILD_DIR)/$(CURRENT_NAME).ttf \
		$(BUILD_DIR)/$(CURRENT_NAME).otf

MAC_TEST_DIR = $(BUILD_DIR)/mac-test-100
MAC_TEST_GRAPHICS = PUA-Square-Braille-Mac-Test-100
MAC_TEST_TEXT = PUA-Square-Braille-Text-Mac-Test-100
MAC_TEST_CURRENT = Square-Braille-Unicode-Text-Seamless-Mac-Test-100
MAC_TEST_FAMILY = Square Braille Unicode Text Seamless Mac Test 100
MAC_TEST_TEXT_SOURCE = fonts/current/$(CURRENT_NAME).ttf

mac-test-100: $(MAC_TEST_DIR)/$(MAC_TEST_CURRENT).ttf

$(MAC_TEST_DIR)/$(MAC_TEST_GRAPHICS).ttf:
	mkdir -p $(MAC_TEST_DIR)
	$(FONTFORGE) -lang=py -script src/font/generate_font.py \
		--font-name "PUA Square Braille Mac Test 100" --version 1.4-test100 \
		--edge-overfill 100 --output-dir $(MAC_TEST_DIR)

$(MAC_TEST_DIR)/$(MAC_TEST_TEXT).ttf: $(MAC_TEST_DIR)/$(MAC_TEST_GRAPHICS).ttf
	test -f "$(MAC_TEST_TEXT_SOURCE)"
	$(FONTFORGE) -lang=py -script src/font/add_text_to_font.py \
		--graphics-font $< --text-font "$(MAC_TEST_TEXT_SOURCE)" \
		--font-name "PUA Square Braille Text Mac Test 100" \
		--version 1.4-test100 --output-dir $(MAC_TEST_DIR)

$(MAC_TEST_DIR)/$(MAC_TEST_CURRENT).ttf: $(MAC_TEST_DIR)/$(MAC_TEST_TEXT).ttf
	$(PYTHON) src/font/map_unicode_braille.py $< $@ \
		--family "$(MAC_TEST_FAMILY)" --version 1.4-test100 \
		--description "macOS rasterization test build with 100-unit exterior overfill"

verify-mac-test-100: mac-test-100
	$(PYTHON) src/font/verify_unicode_braille.py \
		--family "$(MAC_TEST_FAMILY)" \
		$(MAC_TEST_DIR)/$(MAC_TEST_CURRENT).ttf

clean:
	rm -rf -- $(BUILD_DIR)
