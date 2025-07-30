kicad-cli := require("kicad-cli")

kicad_demo := "tests/functional/data/pcb_files/simple_2layer/udb.kicad_pcb"
has_inkview := `command -v inkview >/dev/null 2>&1 && echo "yes" || echo "no"`
has_firefox := `command -v firefox >/dev/null 2>&1 && echo "yes" || echo "no"`
svg_viewer := if has_inkview == "yes" {
  "inkview"
} else if has_firefox == "yes" {
  "firefox"
} else {
  "echo 'Warning: Neither inkview nor firefox found. Cannot open SVG.'"
}
bash_flags := if env("CLAUDECODE", "0") == "1" {
  "-euo pipefail"
} else {
  "-euxo pipefail"
}

clean-venv:
  rm -rf .env

# this environment is required for running demos and functional tests
venv:
  #!/usr/bin/env bash
  set {{ bash_flags }}
  python -m venv --system-site-packages .env
  . .env/bin/activate
  python -m pip install -e .
  python -m pip install -r dev-requirements.txt

preview-svg path:
  @if [ "${CLAUDECODE:-0}" = "1" ]; then \
    echo "SVG content (first 20 lines):"; head -20 "{{ path }}"; \
    else {{ svg_viewer }} "{{ path }}"; \
  fi

demo-simple2layer:
  #!/usr/bin/env bash
  set {{ bash_flags }}
  . .env/bin/activate
  rm -rf output_test
  # copper layers listed from front to bottom order, which means that bottom will be on top (first visible)
  kicad-svg-extras --layers "F.Cu,In1.Cu,In2.Cu,B.Cu,F.SilkS,B.SilkS,Edge.Cuts" \
    --skip-zones --log-level DEBUG \
    --background-color "black" \
    --keep-intermediates {{ kicad_demo }} output_test
  just preview-svg output_test/colored*.svg

demo-simple2layer-css:
  #!/usr/bin/env bash
  set {{ bash_flags }}
  . .env/bin/activate
  rm -rf output_test_css
  kicad-svg-extras --layers "F.Cu,In1.Cu,In2.Cu,B.Cu,F.SilkS,B.SilkS,Edge.Cuts" \
    --skip-zones --log-level DEBUG \
    --background-color "black" \
    --use-css-classes \
    --keep-intermediates {{ kicad_demo }} output_test_css
  just preview-svg output_test_css/colored*.svg


svg-mm-to-cm svg_file:
  sed -i -E 's/(width|height)="([0-9]*\.[0-9]*)mm"/\1="\2cm"/g' {{svg_file}}

svg-fix-area svg_file:
  inkscape --export-type="svg" --export-area-drawing -o {{svg_file}} {{svg_file}}

demo-kicad-cli-comparison:
  #!/usr/bin/env bash
  set {{ bash_flags }}
  . .env/bin/activate
  rm -rf output_test_css
  kicad-svg-extras --layers "F.Cu,B.Cu,Edge.Cuts" \
    --no-background \
    {{ kicad_demo }} output_test_tmp
  mv output_test_tmp/colored_F_Cu_B_Cu_Edge_Cuts.svg resources/kicad-svg-extras.svg

  {{ kicad-cli }} pcb export svg --layers "F.Cu,B.Cu,Edge.Cuts" \
    --exclude-drawing-sheet --fit-page-to-board \
    --output resources/kicad-cli.svg {{ kicad_demo }}

  just svg-mm-to-cm resources/kicad-svg-extras.svg
  just svg-mm-to-cm resources/kicad-cli.svg
  just svg-fix-area resources/kicad-cli.svg

test-unit:
  hatch run test-unit

test-functional filter="":
  #!/usr/bin/env bash
  set {{ bash_flags }}
  . .env/bin/activate
  python -m pytest -m functional --html=output_test/functional_report.html --self-contained-html {{ filter }} tests/

test-functional-generate-refs:
  #!/usr/bin/env bash
  set {{ bash_flags }}
  . .env/bin/activate
  python -m pytest -m functional --generate-references tests/

test-unit-cov:
  hatch run cov

lint:
  hatch run lint:all

alias fmt := format
format:
  hatch run lint:fmt
