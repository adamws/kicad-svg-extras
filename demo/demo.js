let metadata = null;
let currentSelection = null;
let originalSvgStyles = null; // Store original SVG styles for restoration

// Store custom user-selected colors for nets
let customNetColors = new Map(); // netName -> hexColor

// SVG zoom and pan state
let svgZoom = 1;
let svgPanX = 0;
let svgPanY = 0;
let isPanning = false;
let lastPanX = 0;
let lastPanY = 0;
let originalViewBox = null;

// Layer visibility state
let visibleLayers = new Set();

// KiCad-style color manipulation functions
function parseColor(hexColor) {
    const hex = hexColor.replace('#', '');
    return {
        r: parseInt(hex.substr(0, 2), 16) / 255.0,
        g: parseInt(hex.substr(2, 2), 16) / 255.0,
        b: parseInt(hex.substr(4, 2), 16) / 255.0
    };
}

function colorToHex(color) {
    const r = Math.round(Math.max(0, Math.min(1, color.r)) * 255);
    const g = Math.round(Math.max(0, Math.min(1, color.g)) * 255);
    const b = Math.round(Math.max(0, Math.min(1, color.b)) * 255);
    return '#' + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
}

function getBrightness(color) {
    return (color.r + color.g + color.b) / 3.0;
}

function brightenColor(color, factor) {
    return {
        r: color.r * (1.0 - factor) + factor,
        g: color.g * (1.0 - factor) + factor,
        b: color.b * (1.0 - factor) + factor
    };
}

function darkenColor(color, factor) {
    return {
        r: color.r * (1.0 - factor),
        g: color.g * (1.0 - factor),
        b: color.b * (1.0 - factor)
    };
}

// KiCad's selection highlighting algorithm
function getKiCadHighlightColor(hexColor) {
    const color = parseColor(hexColor);
    const brightness = getBrightness(color);
    const selectFactor = 0.7; // KiCad's typical selection factor

    // Skip brightening for very dark colors (like KiCad does)
    if (brightness < 0.05) {
        return hexColor;
    }

    // Linear brightening doesn't work well for colors near white
    let factor = (selectFactor * 0.5) + Math.pow(brightness, 3);
    factor = Math.min(1.0, factor);

    let highlightedColor = brightenColor(color, factor);

    // If we can't brighten much more, fallback to darkening with blue glow
    if (Math.abs(getBrightness(highlightedColor) - brightness) < 0.05) {
        highlightedColor = darkenColor(color, selectFactor * 0.4);
        // Add blue glow effect
        highlightedColor.b = color.b * (1.0 - factor) + factor;
    }

    return colorToHex(highlightedColor);
}

// Parse colors from SVG CSS for each class
function parseColorsFromSvgCss(svgStyles) {
    const colorMap = new Map();

    // Find all CSS class rules with colors
    const classRules = svgStyles.match(/\.[a-zA-Z0-9\-_]+\s*\{[^}]*\}/g);

    if (classRules) {
        classRules.forEach(rule => {
            const classMatch = rule.match(/\.([a-zA-Z0-9\-_]+)\s*\{([^}]*)\}/);
            if (classMatch) {
                const className = classMatch[1];
                const ruleContent = classMatch[2];

                // Extract fill and stroke colors
                const fillMatch = ruleContent.match(/fill:\s*([^;]+)/);
                const strokeMatch = ruleContent.match(/stroke:\s*([^;]+)/);

                colorMap.set(className, {
                    fill: fillMatch ? fillMatch[1].trim() : null,
                    stroke: strokeMatch ? strokeMatch[1].trim() : null
                });
            }
        });
    }

    return colorMap;
}

// Determine which layers a net actually exists on by checking for SVG elements
function getNetActualLayers(netName, netInfo) {
    const svg = document.querySelector('svg');
    if (!svg) return [];

    const actualLayers = [];

    // Check each layer's CSS class to see if there are elements
    Object.entries(netInfo.css_classes).forEach(([layer, cssClass]) => {
        const elements = svg.querySelectorAll(`.${cssClass}`);
        if (elements.length > 0) {
            actualLayers.push(layer);
        }
    });

    return actualLayers;
}

// Layer visibility control functions
function populateLayerControls() {
    const layerControls = document.getElementById('layerControls');
    layerControls.innerHTML = '';

    if (!metadata || !metadata.copper_layers) return;

    // Initialize all layers as visible
    visibleLayers.clear();
    metadata.copper_layers.forEach(layer => {
        visibleLayers.add(layer);
    });

    // Create toggle button for each layer
    metadata.copper_layers.forEach(layer => {
        const button = document.createElement('button');
        button.className = 'layer-toggle active';
        button.textContent = layer;
        button.onclick = () => toggleLayer(layer);
        layerControls.appendChild(button);
    });
}

function toggleLayer(layerName) {
    if (visibleLayers.has(layerName)) {
        visibleLayers.delete(layerName);
    } else {
        visibleLayers.add(layerName);
    }

    // Update button appearance
    const buttons = document.querySelectorAll('.layer-toggle');
    buttons.forEach(button => {
        if (button.textContent === layerName) {
            button.classList.toggle('active', visibleLayers.has(layerName));
        }
    });

    // Update SVG layer visibility
    updateLayerVisibility();

    // Re-populate net list to show only nets on visible layers
    populateNetList();
}

function updateLayerVisibility() {
    const svg = document.querySelector('svg');
    if (!svg || !metadata) return;

    // Get or create layer visibility style element
    let layerVisibilityStyle = document.getElementById('layer-visibility-styles');
    if (!layerVisibilityStyle) {
        layerVisibilityStyle = document.createElement('style');
        layerVisibilityStyle.id = 'layer-visibility-styles';
        document.head.appendChild(layerVisibilityStyle);
    }

    // Create CSS rules to hide invisible layers
    let cssRules = '';

    // For each layer, if it's not visible, hide all its CSS classes
    metadata.copper_layers.forEach(layer => {
        if (!visibleLayers.has(layer)) {
            // Hide all CSS classes for this layer
            Object.values(metadata.nets).forEach(netInfo => {
                if (netInfo.css_classes && netInfo.css_classes[layer]) {
                    const cssClass = netInfo.css_classes[layer];
                    cssRules += `svg .${cssClass} { display: none !important; }\n`;
                }
            });
        }
    });

    layerVisibilityStyle.textContent = cssRules;
    console.log('Updated layer visibility:', Array.from(visibleLayers));
}

// SVG zoom and pan functions
function applySvgTransform() {
    const svg = document.querySelector('svg');
    if (!svg || !originalViewBox) return;

    const [x, y, width, height] = originalViewBox;
    const scaledWidth = width / svgZoom;
    const scaledHeight = height / svgZoom;
    const newX = x - svgPanX + (width - scaledWidth) / 2;
    const newY = y - svgPanY + (height - scaledHeight) / 2;

    svg.setAttribute('viewBox', `${newX} ${newY} ${scaledWidth} ${scaledHeight}`);
}

function resetSvgView() {
    // Reset zoom and pan
    svgZoom = 1;
    svgPanX = 0;
    svgPanY = 0;
    applySvgTransform();

    // Reset custom net colors
    customNetColors.clear();

    // Reset layer selections - make all layers visible
    if (metadata && metadata.copper_layers) {
        visibleLayers.clear();
        metadata.copper_layers.forEach(layer => {
            visibleLayers.add(layer);
        });

        // Update button appearances to show all as active
        const buttons = document.querySelectorAll('.layer-toggle');
        buttons.forEach(button => {
            button.classList.add('active');
        });

        // Update layer visibility and net list
        updateLayerVisibility();
        populateNetList();
    }

    // Clear any current selection and restore original colors
    clearSelection();
}

function setupSvgInteractions() {
    const svg = document.querySelector('svg');
    if (!svg) return;

    // Store original viewBox
    const viewBox = svg.getAttribute('viewBox');
    if (viewBox) {
        originalViewBox = viewBox.split(' ').map(parseFloat);
    }

    // Zoom with mouse wheel
    svg.addEventListener('wheel', (e) => {
        e.preventDefault();

        const rect = svg.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        // Convert mouse position to normalized coordinates (0-1)
        const normalizedX = mouseX / rect.width;
        const normalizedY = mouseY / rect.height;

        const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
        const oldZoom = svgZoom;
        const newZoom = Math.max(0.1, Math.min(10, svgZoom * zoomFactor));

        if (newZoom !== oldZoom) {
            // Calculate the zoom center offset
            const zoomChange = newZoom / oldZoom;

            // Adjust pan to zoom toward mouse position
            // This keeps the point under the mouse cursor stationary
            const viewWidth = originalViewBox[2] / oldZoom;
            const viewHeight = originalViewBox[3] / oldZoom;

            svgPanX += (normalizedX - 0.5) * viewWidth * (1 - 1/zoomChange);
            svgPanY += (normalizedY - 0.5) * viewHeight * (1 - 1/zoomChange);

            svgZoom = newZoom;
            applySvgTransform();
        }
    });

    // Pan with mouse drag
    svg.addEventListener('mousedown', (e) => {
        if (e.button === 0) { // Left mouse button
            isPanning = true;
            lastPanX = e.clientX;
            lastPanY = e.clientY;
            svg.style.cursor = 'grabbing';
            e.preventDefault();
        }
    });

    document.addEventListener('mousemove', (e) => {
        if (isPanning) {
            const rect = svg.getBoundingClientRect();
            const deltaX = (e.clientX - lastPanX) / rect.width * originalViewBox[2] / svgZoom;
            const deltaY = (e.clientY - lastPanY) / rect.height * originalViewBox[3] / svgZoom;

            svgPanX += deltaX;
            svgPanY += deltaY;

            lastPanX = e.clientX;
            lastPanY = e.clientY;

            applySvgTransform();
        }
    });

    document.addEventListener('mouseup', (e) => {
        if (isPanning) {
            isPanning = false;
            svg.style.cursor = 'grab';
        }
    });

    // Set initial cursor
    svg.style.cursor = 'grab';
}

// Load SVG and metadata
async function loadDemo() {
    try {
        // Load metadata
        const metadataResponse = await fetch('metadata.json');
        metadata = await metadataResponse.json();

        // Load SVG
        const svgResponse = await fetch('demo.svg');
        const svgText = await svgResponse.text();

        document.getElementById('svgContainer').innerHTML = svgText;

        // Store original SVG styles for restoration
        const svgStyleElement = document.querySelector('svg style');
        if (svgStyleElement) {
            originalSvgStyles = svgStyleElement.textContent;
            console.log('Stored original SVG styles');
        }

        // Setup SVG zoom and pan interactions
        setupSvgInteractions();

        // Populate layer controls
        populateLayerControls();

        // Populate net list
        populateNetList();

        // Apply any custom colors that might be set
        applyCustomColors();

    } catch (error) {
        console.error('Error loading demo:', error);
        document.getElementById('svgContainer').innerHTML =
            '<p style="color: red;">Error loading demo files. Please ensure demo.svg and metadata.json are available.</p>';
    }
}

function populateNetList() {
    const netList = document.getElementById('netList');
    netList.innerHTML = '';

    // Sort nets by name, but put power/ground nets first
    const nets = Object.keys(metadata.nets).sort((a, b) => {
        const powerNets = ['VCC', 'VDD', 'VBUS', 'GND', 'GROUND'];
        const aIsPower = powerNets.some(p => a.toUpperCase().includes(p));
        const bIsPower = powerNets.some(p => b.toUpperCase().includes(p));

        if (aIsPower && !bIsPower) return -1;
        if (!aIsPower && bIsPower) return 1;
        return a.localeCompare(b);
    });

    nets.forEach(netName => {
        const netInfo = metadata.nets[netName];
        if (netName === '<no_net>') return; // Skip no-net

        // Get layers where this net actually exists
        const actualLayers = getNetActualLayers(netName, netInfo);

        // Filter to only show layers that are currently visible
        const visibleActualLayers = actualLayers.filter(layer => visibleLayers.has(layer));

        // Only show the net if it exists on at least one visible layer
        if (visibleActualLayers.length === 0) return;

        // Check if user has set a custom color for this net
        let uniqueColors;
        if (customNetColors.has(netName)) {
            // Use custom color for all layers (like KiCad does)
            uniqueColors = [customNetColors.get(netName)];
        } else {
            // Get actual colors for each visible layer from SVG CSS
            const originalColors = parseColorsFromSvgCss(originalSvgStyles);
            const layerColors = [];

            visibleActualLayers.forEach(layer => {
                const cssClass = netInfo.css_classes[layer];
                if (cssClass && originalColors.has(cssClass)) {
                    const classColors = originalColors.get(cssClass);
                    if (classColors.fill) {
                        layerColors.push(classColors.fill);
                    }
                }
            });

            // Remove duplicates and fallback to generic color if no layer colors found
            uniqueColors = [...new Set(layerColors)];
            if (uniqueColors.length === 0) {
                uniqueColors.push(netInfo.color);
            }
        }

        const li = document.createElement('li');
        li.className = 'net-item';

        // Create color display - single color or multiple colors
        let colorDisplay;
        if (uniqueColors.length === 1) {
            colorDisplay = `<div class="net-color" style="background-color: ${uniqueColors[0]}" onclick="openColorPickerForNet('${netName}', event)"></div>`;
        } else {
            // Multiple colors - create a split color display (but still clickable for custom color)
            const colorWidth = 100 / uniqueColors.length;
            const colorStrips = uniqueColors.map((color, index) =>
                `<div class="net-color-strip" style="background-color: ${color}; width: ${colorWidth}%"></div>`
            ).join('');
            colorDisplay = `<div class="net-color net-color-multi" onclick="openColorPickerForNet('${netName}', event)">${colorStrips}</div>`;
        }

        li.innerHTML = `
            ${colorDisplay}
            <div class="net-content" onclick="selectNet('${netName}')">
                <div class="net-name">${netName}</div>
                <div class="layer-badges">
                    ${visibleActualLayers.map(layer =>
                        `<span class="layer-badge">${layer}</span>`
                    ).join('')}
                </div>
            </div>
        `;

        netList.appendChild(li);
    });
}

function selectNet(netName) {
    // If clicking the same net, deselect it
    if (currentSelection === netName) {
        clearSelection();
        return;
    }

    // Clear previous selection
    clearSelection();

    // Mark as selected
    currentSelection = netName;

    // Update UI
    const netItems = document.querySelectorAll('.net-item');
    netItems.forEach(item => {
        const name = item.querySelector('.net-name').textContent;
        if (name === netName) {
            item.classList.add('selected');
        }
    });

    // Apply highlighting to SVG
    highlightNet(netName);
}

function highlightNet(netName) {
    const svg = document.querySelector('svg');
    const svgStyleElement = svg ? svg.querySelector('style') : null;

    if (!svg || !svgStyleElement || !metadata || !originalSvgStyles) {
        console.log('Missing SVG, style element, metadata, or original styles');
        return;
    }

    const netInfo = metadata.nets[netName];
    if (!netInfo) {
        console.log('Net info not found for:', netName);
        return;
    }

    // Parse original colors from SVG CSS
    const originalColors = parseColorsFromSvgCss(originalSvgStyles);

    // Start with custom colors applied, then add highlighting
    let modifiedStyles = originalSvgStyles;

    // First apply custom colors
    customNetColors.forEach((customColor, customNetName) => {
        const customNetInfo = metadata.nets[customNetName];
        if (!customNetInfo) return;

        Object.values(customNetInfo.css_classes).forEach(cssClass => {
            const classRuleRegex = new RegExp(`(\\.${cssClass}\\s*\\{[^}]*\\})`, 'g');
            modifiedStyles = modifiedStyles.replace(classRuleRegex, (match) => {
                let result = match;
                if (result.includes('fill:')) {
                    result = result.replace(/fill:\s*[^;]+/g, `fill: ${customColor}`);
                }
                if (result.includes('stroke:') && !result.includes('stroke: none')) {
                    result = result.replace(/stroke:\s*[^;]+/g, `stroke: ${customColor}`);
                }
                return result;
            });
        });
    });

    // Then apply highlighting for the selected net
    Object.values(netInfo.css_classes).forEach(cssClass => {
        const elements = svg.querySelectorAll(`.${cssClass}`);
        console.log(`Found ${elements.length} elements for class: ${cssClass}`);

        if (elements.length > 0) {
            // Check if this net has a custom color
            const hasCustomColor = customNetColors.has(netName);
            const customColor = hasCustomColor ? customNetColors.get(netName) : null;

            const originalClassColors = originalColors.get(cssClass);
            if (originalClassColors || hasCustomColor) {
                // Use custom color if available, otherwise use original colors
                const baseColorFill = hasCustomColor ? customColor : originalClassColors.fill;
                const baseColorStroke = hasCustomColor ? customColor : originalClassColors.stroke;

                // Calculate highlight colors based on base colors
                const highlightFill = baseColorFill ? getKiCadHighlightColor(baseColorFill) : null;
                const highlightStroke = baseColorStroke ? getKiCadHighlightColor(baseColorStroke) : null;

                console.log(`${cssClass}: fill ${baseColorFill} -> ${highlightFill}, stroke ${baseColorStroke} -> ${highlightStroke}`);

                // Replace colors in CSS rule for this specific class
                const classRegex = new RegExp(`(\\.${cssClass}\\s*\\{[^}]*)(fill:\\s*[^;]+|stroke:\\s*[^;]+)([^}]*\\})`, 'gi');
                modifiedStyles = modifiedStyles.replace(classRegex, (match) => {
                    let result = match;
                    if (highlightFill && (originalClassColors.fill || hasCustomColor)) {
                        result = result.replace(/fill:\s*[^;]+/gi, `fill: ${highlightFill}`);
                    }
                    if (highlightStroke && (originalClassColors.stroke || hasCustomColor)) {
                        result = result.replace(/stroke:\s*[^;]+/gi, `stroke: ${highlightStroke}`);
                    }
                    return result;
                });
            }
        }
    });

    // Apply the modified styles to the SVG
    svgStyleElement.textContent = modifiedStyles;
    console.log('Modified SVG styles for per-layer highlighting');
}

function clearSelection() {
    currentSelection = null;

    // Clear UI selection
    document.querySelectorAll('.net-item').forEach(item => {
        item.classList.remove('selected');
    });

    // Apply custom colors (without highlighting)
    applyCustomColors();
}

// Apply custom net colors by modifying CSS rules (persistent)
function applyCustomColors() {
    const svg = document.querySelector('svg');
    const svgStyleElement = svg ? svg.querySelector('style') : null;

    if (!svg || !svgStyleElement || !metadata || !originalSvgStyles) {
        console.log('Missing SVG, style element, metadata, or original styles');
        return;
    }

    // Start with original styles
    let modifiedStyles = originalSvgStyles;

    // Apply custom colors for each net that has them
    customNetColors.forEach((customColor, netName) => {
        const netInfo = metadata.nets[netName];
        if (!netInfo) return;

        // Replace colors for each CSS class of this net
        Object.values(netInfo.css_classes).forEach(cssClass => {
            const elements = svg.querySelectorAll(`.${cssClass}`);
            if (elements.length > 0) {
                console.log(`Applying custom color ${customColor} to class ${cssClass}`);

                // Find and replace the CSS rule for this specific class
                const classRuleRegex = new RegExp(`(\\.${cssClass}\\s*\\{[^}]*\\})`, 'g');
                modifiedStyles = modifiedStyles.replace(classRuleRegex, (match) => {
                    let result = match;
                    // Replace fill color if it exists
                    if (result.includes('fill:')) {
                        result = result.replace(/fill:\s*[^;]+/g, `fill: ${customColor}`);
                    }
                    // Replace stroke color if it exists and is not 'none'
                    if (result.includes('stroke:') && !result.includes('stroke: none')) {
                        result = result.replace(/stroke:\s*[^;]+/g, `stroke: ${customColor}`);
                    }
                    return result;
                });
            }
        });
    });

    // Apply the modified styles to the SVG
    svgStyleElement.textContent = modifiedStyles;
    console.log('Applied custom colors persistently');
}

// Color picker functionality
function openColorPickerForNet(netName, event) {
    event.stopPropagation(); // Prevent net selection when clicking color

    const colorPicker = document.getElementById('netColorPicker');

    // Set current color as default
    const currentColor = customNetColors.get(netName) || getNetDisplayColor(netName);
    colorPicker.value = currentColor;

    // Set up color change handler
    colorPicker.onchange = function() {
        customNetColors.set(netName, colorPicker.value);
        populateNetList(); // Refresh the net list to show new color
        applyCustomColors(); // Apply the custom color to SVG

        // If this net is currently selected, update the highlighting
        if (currentSelection === netName) {
            highlightNet(netName);
        }
    };

    // Trigger the color picker
    colorPicker.click();
}

// Get the display color for a net (custom color or original)
function getNetDisplayColor(netName) {
    if (customNetColors.has(netName)) {
        return customNetColors.get(netName);
    }

    const netInfo = metadata.nets[netName];
    if (!netInfo) return '#C83434'; // fallback

    // Get actual layers and colors from SVG CSS
    const actualLayers = getNetActualLayers(netName, netInfo);
    const visibleActualLayers = actualLayers.filter(layer => visibleLayers.has(layer));

    if (visibleActualLayers.length === 0) return netInfo.color;

    const originalColors = parseColorsFromSvgCss(originalSvgStyles);
    const layerColors = [];

    visibleActualLayers.forEach(layer => {
        const cssClass = netInfo.css_classes[layer];
        if (cssClass && originalColors.has(cssClass)) {
            const classColors = originalColors.get(cssClass);
            if (classColors.fill) {
                layerColors.push(classColors.fill);
            }
        }
    });

    // Return first unique color or fallback
    const uniqueColors = [...new Set(layerColors)];
    return uniqueColors.length > 0 ? uniqueColors[0] : netInfo.color;
}

// SVG Export functionality
function exportCustomizedSvg() {
    try {
        const svg = document.querySelector('svg');
        if (!svg) {
            console.error('No SVG found to export');
            return;
        }

        // Create a clone of the SVG for export
        const exportSvg = cloneSvgWithCustomColors(svg);

        // Apply current viewport (zoom/pan) to the export
        applyViewboxToExport(exportSvg);

        // Remove elements from hidden layers
        removeHiddenLayers(exportSvg);

        // Clean up demo-specific artifacts
        cleanSvgForExport(exportSvg);

        // Download the customized SVG
        downloadSvgFile(exportSvg);

    } catch (error) {
        console.error('Error exporting SVG:', error);
        alert('Error exporting SVG file. Please check the console for details.');
    }
}

function cloneSvgWithCustomColors(originalSvg) {
    // Clone the SVG element
    const clonedSvg = originalSvg.cloneNode(true);

    // Parse original colors from SVG CSS to preserve them
    const originalColors = parseColorsFromSvgCss(originalSvgStyles);

    // First, convert all CSS colors to inline attributes (preserve original colors)
    if (metadata && metadata.nets) {
        Object.entries(metadata.nets).forEach(([netName, netInfo]) => {
            if (!netInfo.css_classes) return;

            Object.values(netInfo.css_classes).forEach(cssClass => {
                const elements = clonedSvg.querySelectorAll(`.${cssClass}`);
                const classColors = originalColors.get(cssClass);

                if (elements.length > 0 && classColors) {
                    elements.forEach(element => {
                        // Apply original CSS colors as inline attributes
                        if (classColors.fill && classColors.fill !== 'none') {
                            element.setAttribute('fill', classColors.fill);
                        }
                        if (classColors.stroke && classColors.stroke !== 'none') {
                            element.setAttribute('stroke', classColors.stroke);
                        }
                    });
                }
            });
        });
    }

    // Then override with custom colors where they exist
    customNetColors.forEach((customColor, netName) => {
        const netInfo = metadata.nets[netName];
        if (!netInfo) return;

        // Apply custom color to all elements of each CSS class for this net
        Object.values(netInfo.css_classes).forEach(cssClass => {
            const elements = clonedSvg.querySelectorAll(`.${cssClass}`);
            elements.forEach(element => {
                // Override with custom colors
                element.setAttribute('fill', customColor);

                // Only override stroke if element originally had a stroke (not 'none')
                const originalClassColors = originalColors.get(cssClass);
                if (originalClassColors && originalClassColors.stroke && originalClassColors.stroke !== 'none') {
                    element.setAttribute('stroke', customColor);
                }
            });
        });
    });

    return clonedSvg;
}

function applyViewboxToExport(exportSvg) {
    // Apply the current viewBox transformation to maintain zoom/pan
    const currentViewBox = document.querySelector('svg').getAttribute('viewBox');
    if (currentViewBox) {
        exportSvg.setAttribute('viewBox', currentViewBox);
    }
}

function removeHiddenLayers(exportSvg) {
    if (!metadata || !metadata.copper_layers) return;

    // Remove elements belonging to hidden layers
    metadata.copper_layers.forEach(layer => {
        if (!visibleLayers.has(layer)) {
            // Find all nets and their CSS classes for this layer
            Object.values(metadata.nets).forEach(netInfo => {
                if (netInfo.css_classes && netInfo.css_classes[layer]) {
                    const cssClass = netInfo.css_classes[layer];
                    const elementsToRemove = exportSvg.querySelectorAll(`.${cssClass}`);
                    elementsToRemove.forEach(element => element.remove());
                }
            });
        }
    });
}

function cleanSvgForExport(exportSvg) {
    // Remove the internal style element (we've converted colors to inline)
    const styleElement = exportSvg.querySelector('style');
    if (styleElement) {
        styleElement.remove();
    }

    // Remove any demo-specific IDs or classes
    exportSvg.removeAttribute('id');

    // Ensure proper SVG namespace
    exportSvg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    if (exportSvg.getAttribute('xmlns:xlink')) {
        exportSvg.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');
    }
}

function downloadSvgFile(exportSvg) {
    // Serialize the SVG to string
    const serializer = new XMLSerializer();
    let svgString = serializer.serializeToString(exportSvg);

    // Add XML declaration for proper SVG format
    svgString = '<?xml version="1.0" encoding="UTF-8"?>\n' + svgString;

    // Create blob and download
    const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);

    // Create temporary download link
    const downloadLink = document.createElement('a');
    downloadLink.href = url;

    // Generate filename with timestamp
    const timestamp = new Date().toISOString().slice(0, 19).replace(/[:.]/g, '-');
    const hasCustomColors = customNetColors.size > 0;
    const suffix = hasCustomColors ? '-customized' : '';
    downloadLink.download = `pcb-demo${suffix}-${timestamp}.svg`;

    // Trigger download
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);

    // Clean up object URL
    URL.revokeObjectURL(url);

    console.log(`SVG exported successfully: ${downloadLink.download}`);
}

// Load demo when page loads
document.addEventListener('DOMContentLoaded', loadDemo);
