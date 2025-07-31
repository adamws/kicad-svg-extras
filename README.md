<div align="center">

# kicad-svg-extras

_Generate colored SVG files from KiCad PCB files with advanced styling options._

[![CI - Main](https://github.com/adamws/kicad-svg-extras/actions/workflows/ci.yml/badge.svg)](https://github.com/adamws/kicad-svg-extras/actions/workflows/ci.yml)
[![Interactive Demo](https://img.shields.io/badge/🎨_Interactive_Demo-Try_Now-blue)](https://adamws.github.io/kicad-svg-extras/)

</div>

## Motivation

The `kicad-svg-extras` tool extends KiCad's built-in SVG export capabilities by adding support for custom net colors, CSS-based styling, and advanced color management. While `kicad-cli` provides basic SVG export, this tool respects per-net color settings defined in your PCB project and offers flexible styling options for web integration.

<table>
    <tr>
        <td colspan="2" align="center"><img src="resources/pcbnew_window.png" width="80%"/></td>
    </tr>
    <tr>
        <td style="width:50%" align="center"><b>kicad-svg-extras</b></td>
        <td style="width:50%" align="center"><b>kicad-cli pcb export svg</b></td>
    </tr>
    <tr>
        <td align="center"><img src="resources/kicad-svg-extras.svg" width="50%"/></td>
        <td align="center"><img src="resources/kicad-cli.svg" width="50%"/></td>
    </tr>
</table>

## Features

1. 🎨 **Color-Aware SVG Generation**
    - **Project Color Integration**: Automatically reads and applies net colors from your KiCad project file
    - **Custom Color Override**: Set specific colors for individual nets via command line or JSON configuration
1. 🌐 **Web-Ready CSS Styling**
    - **CSS Class Generation**: Generate SVGs with CSS classes for each net
    - **Metadata Export**: Export CSS class mappings for easy integration
    - **[Live Interactive Demo](https://adamws.github.io/kicad-svg-extras/)**: Try the web features online
1.  ⚙️ **Extra Options**
    - **Fit-to-Content**: Automatic canvas sizing based on board edges
    - **Zone Control**: Option to include or exclude copper zones
    - **Background Customization**: Set custom background colors instead of transparent backgrounds

## Installation

> **Note**: This project is currently in pre-release. It will be published to PyPI soon.

Install using pip:

```bash
pip install git+https://github.com/adamws/kicad-svg-extras.git
```

> [!IMPORTANT]
> The `kicad-svg-extras` python package depends on `pcbnew` package
> which is distributed as part of KiCad installation.
> This means, that on Windows it is **required** to use python bundled with KiCad.
> On Linux, `pcbnew` package should be available globally (this can be verified by
> running `python -c "import pcbnew; print(pcbnew.Version())"`) so it may not work
> inside isolated environment. To install inside virtual environment created with `venv`
> it is required to use `--system-site-package` option when creating this environment.

## Usage

<table>
<tr>
<th colspan="2"><b>Basic Usage - Project Colors</b></th>
</tr>
<tr>
<td>

Generate an SVG using colors defined in your KiCad project:

```bash
kicad-svg-extras --output board.svg board.kicad_pcb
```

This automatically:
- Detects the corresponding `.kicad_pro` file
- Applies net colors from the project's `net_colors` settings
- Processes default layers (F.Cu, B.Cu)

</td>
<td>

<img src="resources/basic-example.svg" width="100%"/>

</td>
</tr>
<tr>
<th colspan="2"><b>Custom Net Colors</b></th>
</tr>
<tr>
<td>

Override specific net colors from the command line
and via `color.json` definition.

```bash
kicad-svg-extras --output board.svg --layers "B.Cu" \
  --ignore-project-colors \
  --net-color "VCC:#fabd2f" --colors colors.json \
  board.kicad_pcb
```

**Supported color formats:**
- Hex: `#FF0000`, `#f00`
- RGB: `rgb(255,0,0)`
- Named: `red`, `green`, `blue`

**colors.json example:**

```json
{
  "net_colors": {
    "N$*": "#b8bb26",
    "VCC": "black",
    "GND": "gray"
  }
}
```

Net names in both `--net-color` and `--colors` json file support wildcards.

</td>
<td>

<img src="resources/color-priority-demo.svg" width="100%"/>

</td>
</tr>
<tr>
<th colspan="2"><b>CSS Mode for Web Integration</b></th>
</tr>
<tr>
<td>

Generate web-ready SVGs with CSS classes:

```bash
kicad-svg-extras --output board.svg \
  --ignore-project-colors \
  --use-css-classes \
  --export-metadata metadata.json \
  board.kicad_pcb
```

**Creates:**
- **board.svg**: SVG with CSS classes like `.net-gnd-f-cu`
- **metadata.json**: Net-to-CSS mappings

</td>
<td>

<img src="demo/demo.svg" width="100%"/></b>
**[Live Interactive Demo](https://adamws.github.io/kicad-svg-extras/)**

</td>
</tr>
</table>

## How It Works

### Color Priority System

Colors are resolved using a clear priority hierarchy:

1. CLI Arguments (Highest Priority)
2. JSON Configuration File
3. KiCad Project File
4. KiCad Theme Defaults (Lowest Priority)

### Processing Workflow

1. **Net Analysis**: Extract all nets from the PCB and determine which layers they appear on
2. **Color Resolution**: Apply the color priority system to assign final colors
3. **PCB Splitting**: Create filtered PCB files for each net group (same color nets are processed together)
4. **SVG Generation**: Use KiCad's plotting API to generate individual SVGs
5. **Color Application**: Apply colors either as direct fill attributes or CSS classes
6. **Layer Merging**: Combine all layers in the correct stacking order

## Development

### Running Tests

```bash
# Unit tests (no KiCad's pcbnew module required)
hatch run test-unit
# Functional tests (requires KiCad's pcbnew module)
hatch run test-functional
```

## Disclaimer

This project has been mostly AI generated using [claude-code](https://github.com/anthropics/claude-code).
