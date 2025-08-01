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

# environment for running demos and tests
venv:
  #!/usr/bin/env bash
  set {{ bash_flags }}
  python -m venv .env
  . .env/bin/activate
  python -m pip install -e .

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
  mkdir -p output_test
  # copper layers listed from front to bottom order, which means that bottom will be on top (first visible)
  kicad-svg-extras --output output_test/result.svg \
    --layers "F.Cu,In1.Cu,In2.Cu,B.Cu,F.SilkS,B.SilkS,Edge.Cuts" \
    --skip-zones --log-level DEBUG \
    --background-color "black" \
    --keep-intermediates {{ kicad_demo }}
  just preview-svg output_test/result.svg

demo-simple2layer-css:
  #!/usr/bin/env bash
  set {{ bash_flags }}
  . .env/bin/activate
  rm -rf output_test_css
  mkdir -p output_test_css
  kicad-svg-extras --output output_test_css/result.svg \
    --layers "F.Cu,In1.Cu,In2.Cu,B.Cu,F.SilkS,B.SilkS,Edge.Cuts" \
    --skip-zones --log-level DEBUG \
    --background-color "black" \
    --use-css-classes \
    --keep-intermediates {{ kicad_demo }}
  just preview-svg output_test_css/result.svg


svg-mm-to-cm svg_file:
  sed -i -E 's/(width|height)="([0-9]*\.[0-9]*)mm"/\1="\2cm"/g' {{svg_file}}

svg-fix-area svg_file:
  inkscape --export-type="svg" --export-area-drawing -o {{svg_file}} {{svg_file}}

demo-kicad-cli-comparison:
  #!/usr/bin/env bash
  set {{ bash_flags }}
  . .env/bin/activate
  kicad-svg-extras --output resources/kicad-svg-extras.svg \
    --layers "F.Cu,B.Cu,Edge.Cuts" \
    --no-background \
    {{ kicad_demo }}

  {{ kicad-cli }} pcb export svg --layers "F.Cu,B.Cu,Edge.Cuts" \
    --exclude-drawing-sheet --fit-page-to-board \
    --output resources/kicad-cli.svg {{ kicad_demo }}

  just svg-mm-to-cm resources/kicad-svg-extras.svg
  just svg-mm-to-cm resources/kicad-cli.svg
  just svg-fix-area resources/kicad-cli.svg

demo-readme1:
  #!/usr/bin/env bash
  set {{ bash_flags }}
  . .env/bin/activate
  kicad-svg-extras --output resources/basic-example.svg {{ kicad_demo }}
  just svg-mm-to-cm resources/basic-example.svg

demo-readme2:
  #!/usr/bin/env bash
  set {{ bash_flags }}
  . .env/bin/activate
  kicad-svg-extras --output resources/color-priority-demo.svg \
    --layers "B.Cu" \
    --ignore-project-colors \
    --net-color "VCC:#fabd2f" \
    --colors resources/color-config-example.json \
    {{ kicad_demo }}
  just svg-mm-to-cm resources/color-priority-demo.svg

demo-interactive:
  #!/usr/bin/env bash
  set {{ bash_flags }}
  . .env/bin/activate
  rm -rf demo/demo.svg demo/metadata.json
  kicad-svg-extras --output demo/demo.svg \
    --use-css-classes \
    --export-metadata demo/metadata.json \
    --ignore-project-colors \
    --layers "F.Cu,B.Cu" \
    --log-level INFO \
    {{ kicad_demo }}
  just svg-mm-to-cm demo/demo.svg
  echo "Interactive demo generated in demo/ directory"
  echo "Open demo/index.html in a web browser to view"

demo-serve port="8000":
  #!/usr/bin/env bash
  set {{ bash_flags }}
  echo "Starting demo server at http://localhost:{{ port }}"
  echo "Press Ctrl+C to stop"
  if command -v python >/dev/null 2>&1; then
    cd demo && python -m http.server {{ port }}
  else
    echo "Python not found. Please serve the demo/ directory with your preferred web server."
    exit 1
  fi

test-unit:
  hatch run test-unit

test-functional filter="":
  hatch run test-functional {{ filter }}

test-functional-generate-refs:
  hatch run test-functional --generate-references

test-unit-cov:
  hatch run cov

lint:
  hatch run lint:all

alias fmt := format
format:
  hatch run lint:fmt
