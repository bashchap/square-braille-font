PYTHON ?= python3
FONTFORGE ?= fontforge
DEJAVU_MONO ?= /usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf
BUILD_DIR ?= build

CURRENT_NAME = Square-Braille-Unicode-Text-Seamless
TEXT_NAME = PUA-Square-Braille-Text-Seamless
GRAPHICS_NAME = PUA-Square-Braille-Seamless

.PHONY: all verify clean

all: $(BUILD_DIR)/$(CURRENT_NAME).ttf $(BUILD_DIR)/$(CURRENT_NAME).otf

$(BUILD_DIR)/$(GRAPHICS_NAME).ttf:
	mkdir -p $(BUILD_DIR)
	$(FONTFORGE) -lang=py -script src/font/generate_font.py \
		--font-name "PUA Square Braille Seamless" --version 1.1 \
		--edge-overfill 60 --output-dir $(BUILD_DIR)

$(BUILD_DIR)/$(TEXT_NAME).ttf: $(BUILD_DIR)/$(GRAPHICS_NAME).ttf
	test -f "$(DEJAVU_MONO)"
	$(FONTFORGE) -lang=py -script src/font/add_text_to_font.py \
		--graphics-font $< --text-font "$(DEJAVU_MONO)" \
		--font-name "PUA Square Braille Text Seamless" --version 1.2 \
		--output-dir $(BUILD_DIR)

$(BUILD_DIR)/$(CURRENT_NAME).ttf: $(BUILD_DIR)/$(TEXT_NAME).ttf
	$(PYTHON) src/font/map_unicode_braille.py $< $@

$(BUILD_DIR)/$(CURRENT_NAME).otf: $(BUILD_DIR)/$(TEXT_NAME).ttf
	$(PYTHON) src/font/map_unicode_braille.py \
		$(BUILD_DIR)/$(TEXT_NAME).otf $@

verify: all
	$(PYTHON) src/font/verify_unicode_braille.py \
		$(BUILD_DIR)/$(CURRENT_NAME).ttf \
		$(BUILD_DIR)/$(CURRENT_NAME).otf

clean:
	rm -rf -- $(BUILD_DIR)

