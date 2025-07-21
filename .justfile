kicad-cli := require("kicad-cli")

kicad_demo := "tests/functional/data/pcb_files/simple_2layer/udb.kicad_pcb"

clean-venv:
  rm -rf .env

# this environment is required for running demos and functional tests
venv:
  #!/usr/bin/env bash
  python -m venv --system-site-packages .env
  . .env/bin/activate
  python -m pip install -e .
  python -m pip install -r dev-requirements.txt

color-demo:
  #!/usr/bin/env bash
  set -euxo pipefail
  . .env/bin/activate
  rm -rf output_test
  kicad-svg-extras --layers "F.Cu,In1.Cu,In2.Cu,B.Cu,F.SilkS,B.SilkS,Edge.Cuts" \
    --skip-zones --log-level DEBUG \
    --net-color "GND:red" --net-color "VCC:blue" --net-color "VPP:green" \
    --fit-to-content --background-color "black" \
    --keep-intermediates {{ kicad_demo }} output_test
  inkview output_test/colored_F_Cu_In1_Cu_In2_Cu_B_Cu.svg

color-demo-css:
  #!/usr/bin/env bash
  set -euxo pipefail
  . .env/bin/activate
  rm -rf output_test_css
  kicad-svg-extras --layers "F.Cu,In1.Cu,In2.Cu,B.Cu,F.SilkS,B.SilkS,Edge.Cuts" \
    --skip-zones --log-level DEBUG \
    --net-color "GND:red" --net-color "VCC:blue" --net-color "VPP:green" \
    --use-css-classes \
    --keep-intermediates {{ kicad_demo }} output_test_css
  inkview output_test_css/colored_F_Cu_In1_Cu_In2_Cu_B_Cu.svg

test-unit:
  hatch run test-unit

test-functional:
  #!/usr/bin/env bash
  set -euxo pipefail
  . .env/bin/activate
  python -m pytest -m functional --html=output_test/functional_report.html --self-contained-html tests/

test-functional-generate-refs:
  #!/usr/bin/env bash
  set -euxo pipefail
  . .env/bin/activate
  python -m pytest -m functional --generate-references tests/

test-unit-cov:
  hatch run cov

lint:
  hatch run lint:all

fmt:
  hatch run lint:fmt
