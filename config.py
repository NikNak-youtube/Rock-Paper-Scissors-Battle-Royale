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

# Possession: the player can right-click an entity to take direct control of
# it, steering with WASD / arrow keys. The controlled entity ignores its AI
# but still collides (and can convert or be converted) like any other.
PLAYER_CONTROL_SPEED = 4.0  # Movement speed of a possessed entity (px/frame)
MAX_ENTITIES = 6000  # Total simulation cap across all types (per-type cap = MAX_ENTITIES // 3)
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

# Shared distance calculation: same-type entities within SHARED_CALC_RADIUS
# reuse one entity's nearest-threat/prey scan instead of recomputing. This is
# an approximation — followers move as if they were at the leader's position
# w.r.t. distant threats, but local repulsion is still computed individually.
SHARED_CALC_ENABLED = True
SHARED_CALC_RADIUS = 80

# Post-conversion growth: newly spawned/converted entities start small and
# attempt to grow once every GROWTH_INTERVAL_FRAMES with GROWTH_CHANCE per
# attempt, gaining GROWTH_INCREMENT pixels each success up to MAX_SIZE.
GROWTH_ENABLED = True
GROWTH_CHANCE = 0.6
GROWTH_INTERVAL_FRAMES = FPS  # 1 second at default FPS
GROWTH_INCREMENT = MAX_SIZE / 5  # 1/5 of the max size per growth tick
GROWTH_START_SIZE = MIN_SIZE

# RGB tint genome: independent of evolution's size/speed budget. On conversion
# the loser inherits the winner's tint with a small per-channel mutation, so
# you can visually trace lineages over time. Tint is applied to the sprite
# via BLEND_RGBA_MULT — values near 255 leave the image alone, lower values
# darken/colorize.
TINT_ENABLED = True
TINT_MUTATION = 2         # max per-channel drift per conversion (±)
TINT_INIT_MIN = 80         # initial random tint floor (avoid muddy darks)
TINT_INIT_MAX = 255

# Communication: same-type entities can broadcast the location of a known
# enemy to nearby allies. Two genetic traits — radius (how far a signal
# carries) and chance (per-entity success probability, used both as the
# sender and the receiver). A signal goes through only if BOTH the sender
# and the receiver pass their chance roll. Inherited independently of the
# size/speed property budget, like tint.
COMM_ENABLED = True
MIN_COMM_RADIUS = 60
MAX_COMM_RADIUS = 250
COMM_CHANCE_MIN = 0.01
COMM_CHANCE_MAX = 0.15
COMM_TRIGGER_CHANCE = 0.30          # chance per frame to attempt broadcast when prey visible
COMM_COOLDOWN_FRAMES = FPS          # 1 broadcast per entity per second
COMM_KNOWLEDGE_DURATION_FRAMES = FPS * 4  # how long a learned location stays "fresh"
COMM_MUTATION = 0.10                # max drift per conversion as fraction of full range

# Colors for each type (fallback if images don't load)
TYPE_COLORS = {
    ROCK: (139, 69, 19),     # Brown
    PAPER: (245, 245, 220),  # Beige
    SCISSORS: (192, 192, 192) # Silver
}
