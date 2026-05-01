"""
Configuration constants for Rock Paper Scissors Battle Royale
"""

import warnings
import numpy as np

# Suppress CuPy warnings about multiple installations
warnings.filterwarnings('ignore', message='.*CuPy.*multiple.*packages.*')
warnings.filterwarnings('ignore', category=UserWarning, module='cupy')

# Try to import CuPy for GPU acceleration
GPU_AVAILABLE = False
cp = np  # Default to NumPy
try:
    import cupy as _cp
    # Test if CuPy actually works by doing a real GPU operation
    # This will fail if CUDA libraries are missing
    _test = _cp.array([1.0, 2.0, 3.0], dtype=_cp.float32)
    _test2 = _cp.array([4.0, 5.0, 6.0], dtype=_cp.float32)
    _test_result = _test + _test2  # Force kernel compilation
    _test_result_cpu = _cp.asnumpy(_test_result)  # Transfer back
    del _test, _test2, _test_result, _test_result_cpu
    cp = _cp
    GPU_AVAILABLE = True
    print("GPU acceleration enabled (CuPy + CUDA)")
except ImportError:
    print("CuPy not available - using CPU (NumPy)")
except Exception as e:
    # CuPy imported but CUDA libraries not working
    print(f"CuPy/CUDA test failed: {type(e).__name__}")
    print("Falling back to CPU (NumPy)")

# Try to import matplotlib for optional graphing
try:
    import matplotlib
    matplotlib.use('TkAgg')  # Use interactive backend
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None
    print("matplotlib not available - graphing disabled")

# Threading settings
NUM_THREADS = 4  # Number of worker threads for entity updates

# Screen settings
DEFAULT_SCREEN_WIDTH = 1200
DEFAULT_SCREEN_HEIGHT = 800
MIN_SCREEN_WIDTH = 800
MIN_SCREEN_HEIGHT = 600
UI_PANEL_WIDTH = 200  # Fixed width for UI panel
FPS = 60

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (128, 128, 128)
DARK_GRAY = (50, 50, 50)
RED = (255, 100, 100)
GREEN = (100, 255, 100)
BLUE = (100, 100, 255)
YELLOW = (255, 255, 100)

# Entity settings
ENTITY_SIZE = 40
ENTITY_SPEED = 2
INITIAL_COUNT = 15  # Initial count per type
SAME_TYPE_REPEL_RADIUS = 50  # Radius for soft collision between same types
SAME_TYPE_REPEL_STRENGTH = 0.5  # How strongly same types push each other away

# Edge behavior settings
EDGE_WRAP = False  # If True, entities wrap around edges; if False, they bounce

# Recording settings
RECORDING_ENABLED = False  # If True, save every frame as PNG for video creation
RECORDING_FOLDER = "recordings"  # Base folder for recordings

# Evolution settings
EVOLUTION_ENABLED = True  # Toggle evolution on/off
MUTATION_RATE = 0.15  # How much properties can mutate (0-1)
PROPERTY_BUDGET = 2.0  # Total budget for all normalized properties
MIN_SIZE = 20  # Minimum entity size
MAX_SIZE = 60  # Maximum entity size
MIN_SPEED = 1.0  # Minimum speed
MAX_SPEED = 4.0  # Maximum speed
MIN_FLEE_DISTANCE = 50  # Minimum flee trigger distance
MAX_FLEE_DISTANCE = 250  # Maximum flee trigger distance
MIN_ATTACK_DISTANCE = 100  # Minimum attack detection distance
MAX_ATTACK_DISTANCE = 400  # Maximum attack detection distance

# Entity types
ROCK = "rock"
PAPER = "paper"
SCISSORS = "scissors"

# Define what beats what
BEATS = {
    ROCK: SCISSORS,
    PAPER: ROCK,
    SCISSORS: PAPER
}

# Reverse lookup: who beats this entity (the threat for each type)
BEATEN_BY = {v: k for k, v in BEATS.items()}

# Spatial grid cell size (pixels). Tune relative to typical query radius —
# larger cells = fewer cells to scan but more entities per cell.
SPATIAL_GRID_CELL_SIZE = 100

# Colors for each type (fallback if images don't load)
TYPE_COLORS = {
    ROCK: (139, 69, 19),     # Brown
    PAPER: (245, 245, 220),  # Beige
    SCISSORS: (192, 192, 192) # Silver
}
