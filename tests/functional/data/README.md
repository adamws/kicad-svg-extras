# Test Data Directory

This directory contains test data for functional testing of kicad-svg-extras.

## Structure

```
tests/data/
├── pcb_files/          # KiCad PCB files for testing
│   ├── simple_2layer/  # Basic 2-layer board
│   ├── simple_4layer/  # Basic Multi-layer board
├── config_files/       # Color configuration files
│   ├── basic_colors.json      # Simple net color mappings
│   └── advanced_nets.json     # Complex patterns and wildcards
└── README.md          # This file
```

## PCB Files (To be added)

PCB test files should be organized by complexity and layer count:

- **simple_2layer/**: Basic 2-layer board
  - origins in [kle2netlist](https://github.com/adamws/kle2netlist)
- **simple_4layer/**: Basic Multi-layer board
  - copied from [UDB-C-EZM](https://github.com/Unified-Daughterboard/UDB-C-EZM)

## Configuration Files

### basic_colors.json
Simple color mappings for common nets:
- GND: Red (#FF0000)
- VCC: Blue (#0000FF)
- 3V3: Green (#00FF00)
- Plus wildcard patterns for DATA*, CLK*, etc.

### advanced_nets.json
Complex configuration with:
- Named colors (red, blue, green)
- Wildcard patterns (USB_*, SPI_*, I2C_*)
- KiCad project format compatibility

## Usage

These files are used by functional tests in `tests/functional/` to:
1. Generate SVG outputs with various CLI options
2. Compare against human-verified reference files
3. Test different layer combinations and color schemes
4. Validate error handling with invalid inputs

## Adding New Test Data

When adding new PCB files:
1. Place in appropriate subdirectory by complexity
2. Include a brief description of the board purpose
3. Generate reference SVG files using current tool version
4. Manually verify reference outputs before committing
5. Add corresponding test cases in functional tests
