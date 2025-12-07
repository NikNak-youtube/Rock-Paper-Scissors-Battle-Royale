# Rock Paper Scissors - Battle Royale 🪨📄✂️

A visually engaging battle royale simulation where rocks, papers, and scissors fight for dominance! Watch as entities chase their prey, flee from threats, and convert defeated opponents to their side.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Pygame](https://img.shields.io/badge/Pygame-2.0+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## 🎮 Gameplay

The simulation follows classic Rock Paper Scissors rules:
- **Rock** beats **Scissors**
- **Scissors** beats **Paper**
- **Paper** beats **Rock**

When two entities collide, the winner converts the loser to its own type. The battle continues until only one type remains!

### Entity Behavior
- **Chase**: Entities actively hunt what they can beat
- **Flee**: Entities run away from what can beat them
- **Soft Collision**: Same-type entities gently push each other apart to prevent clumping
- **Wander**: When no threats or prey are nearby, entities wander randomly

## 🚀 Getting Started

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/NikNak-youtube/Rock-Paper-Sissors-Battle-Royale.git
   cd Rock-Paper-Sissors-Battle-Royale
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install pygame matplotlib
   ```

4. **Run the game**
   ```bash
   python main.py
   ```

## 🎛️ Controls

| Control | Action |
|---------|--------|
| **SPACE** | Pause / Resume simulation |
| **R** | Restart simulation |
| **ESC** | Quit game |
| **Left Click** (game area) | Add random entity at cursor |
| **Drag window edges** | Resize window dynamically |

### UI Buttons
- **Start/Restart** - Reset the simulation
- **Pause/Resume** - Toggle pause state
- **Speed: Nx** - Cycle through speed multipliers (0.5x, 1x, 2x, 4x)
- **Add Rock/Paper/Scissors** - Spawn specific entity types
- **Evolution: ON/OFF** - Toggle evolutionary properties (restarts simulation)
- **Count -/+** - Adjust initial entity count per type (1-500)
- **Graph: ON/OFF** - Toggle population data recording
- **Open Graph** - Open real-time population graph window

## 📁 Project Structure

```
Rock-Paper-Sissors-Battle-Royale/
├── main.py              # Main game file (multithreaded)
├── images/              # Entity images
│   ├── boulder-clipart-transparent-background-rock-1-3961670665.png
│   ├── Paper-Sheet-PNG-Transparent-Background-3062699109.png
│   └── scissors_PNG28-2679021845.png
├── requirements.txt     # Python dependencies
├── .gitignore
└── README.md
```

## ⚙️ Configuration

You can customize the simulation by modifying constants at the top of `main.py`:

```python
# Screen settings
DEFAULT_SCREEN_WIDTH = 1200
DEFAULT_SCREEN_HEIGHT = 800
MIN_SCREEN_WIDTH = 800
MIN_SCREEN_HEIGHT = 600
UI_PANEL_WIDTH = 200
FPS = 60

# Threading settings
NUM_THREADS = 4  # Worker threads for parallel entity updates

# Entity settings
ENTITY_SIZE = 40              # Size of each entity
ENTITY_SPEED = 2              # Base movement speed
INITIAL_COUNT = 15            # Starting count per type
SAME_TYPE_REPEL_RADIUS = 50   # Soft collision radius
SAME_TYPE_REPEL_STRENGTH = 0.5  # Repulsion force strength

# Evolution settings
EVOLUTION_ENABLED = True      # Toggle evolution on/off by default
MUTATION_RATE = 0.15          # How much properties can mutate (0-1)
PROPERTY_BUDGET = 2.0         # Total budget for balanced properties
MIN_SIZE = 20                 # Minimum entity size
MAX_SIZE = 60                 # Maximum entity size
MIN_SPEED = 1.0               # Minimum speed
MAX_SPEED = 4.0               # Maximum speed
MIN_FLEE_DISTANCE = 50        # Minimum flee trigger distance
MAX_FLEE_DISTANCE = 250       # Maximum flee trigger distance
MIN_ATTACK_DISTANCE = 100     # Minimum attack detection distance
MAX_ATTACK_DISTANCE = 400     # Maximum attack detection distance
```

## 🎨 Features

- **Resizable Window** - Drag to resize, UI adapts dynamically
- **Interactive GUI** - Full control panel with buttons and stats
- **Real-time Statistics** - Track entity counts and conversions
- **Speed Control** - Watch in slow-mo or fast-forward the action
- **Custom Images** - Visual representation using PNG images
- **Smooth Animations** - 60 FPS with interpolated movement
- **Soft Collision System** - Entities of the same type naturally spread out
- **Game Over Screen** - Celebratory winner announcement
- **Evolutionary Properties** - Optional evolution system with inheritance and mutation
- **Real-time Graphing** - Live matplotlib population graph in separate window
- **Multithreaded Updates** - Parallel entity processing for large simulations

## 🧵 Multithreading

The simulation uses multithreading for improved performance:

- **Entity Updates**: When entity count exceeds 50, updates are parallelized across multiple worker threads using Python's `ThreadPoolExecutor`
- **Graph Updates**: Real-time graph rendering runs in a separate thread to avoid blocking the main game loop
- **Thread Pool**: Configurable number of worker threads (default: 4)
- **Thread Safety**: Collision detection remains sequential to prevent race conditions

This allows smooth performance even with hundreds of entities on screen.

## 🧬 Evolution System

When evolution is enabled, each entity has individual properties that evolve over time:

| Property | Description | Range |
|----------|-------------|-------|
| **Size** | Physical size of the entity | 20-60 pixels |
| **Speed** | Movement speed | 1.0-4.0 |
| **Flee Distance** | How far away threats trigger fleeing | 50-250 pixels |
| **Attack Distance** | How far away prey is detected | 100-400 pixels |

### Balanced Evolution
Properties are **balanced** - they always sum to the same total. If one property increases, others must decrease:
- Want to be fast? You'll sacrifice size, flee awareness, or attack range
- Every advantage comes with a trade-off
- This creates diverse, specialized entity "builds"

### How Evolution Works
1. **Initial Spawn**: Entities start with random balanced properties
2. **Inheritance**: When an entity wins a collision, the converted entity inherits the winner's properties
3. **Mutation**: Inherited properties mutate slightly (±15% by default), with compensation to maintain balance
4. **Natural Selection**: Over time, successful traits spread through the population

### Emergent Behaviors
- **Aggressive strains**: High speed + high attack distance = effective hunters
- **Defensive strains**: High flee distance + high speed = better survivors
- **Tank builds**: Large size makes it easier to catch prey
- **Scout builds**: Small + fast entities that cover more ground

## 📊 Real-time Graphing

Click **"Open Graph"** to open a live matplotlib window showing population dynamics:

- **X-axis**: Time in seconds
- **Y-axis**: Population count
- **Three lines**: Rock (brown), Paper (gold), Scissors (gray)
- **Auto-scaling**: Axes adjust automatically as data grows
- **Non-blocking**: Graph updates in a separate thread

The graph helps visualize:
- Population oscillations (predator-prey dynamics)
- Extinction events
- Dominant strategy emergence

## 📈 Statistics Display

The UI panel shows:
- Current count of each entity type
- Number of conversions made by each type (in green)
- Total entity count
- Initial count per type setting
- Interactive control buttons

## 🤝 Contributing

Contributions are welcome! Feel free to:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 🙏 Acknowledgments

- Inspired by viral Rock Paper Scissors battle royale simulations
- Built with [Pygame](https://www.pygame.org/) and [Matplotlib](https://matplotlib.org/)

---

Made with ❤️ and Python
