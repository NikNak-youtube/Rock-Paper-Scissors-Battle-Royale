import pygame
import random
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import queue
import numpy as np
import warnings

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
    from matplotlib.animation import FuncAnimation
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("matplotlib not available - graphing disabled")

# Initialize pygame
pygame.init()

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

# Evolution settings
EVOLUTION_ENABLED = True  # Toggle evolution on/off
MUTATION_RATE = 0.15  # How much properties can mutate (0-1)
PROPERTY_BUDGET = 2.0  # Total budget for all normalized properties (each prop is 0-1, 4 props, avg 0.5 each = 2.0)
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

# Colors for each type (fallback if images don't load)
TYPE_COLORS = {
    ROCK: (139, 69, 19),     # Brown
    PAPER: (245, 245, 220),  # Beige
    SCISSORS: (192, 192, 192) # Silver
}

class Entity:
    # Property count for balanced distribution
    NUM_PROPERTIES = 4
    
    def __init__(self, x, y, entity_type, image=None, parent=None, evolution_enabled=True):
        self.x = x
        self.y = y
        self.entity_type = entity_type
        self.base_image = image  # Store original image
        self.image = image
        self.target = None
        self.flee_from = None
        
        # Evolutionary properties (stored as normalized 0-1 values internally)
        if evolution_enabled and parent:
            # Inherit from parent with balanced mutation
            self._inherit_balanced(parent)
        elif evolution_enabled:
            # Random initial properties that sum to PROPERTY_BUDGET
            self._init_random_balanced()
        else:
            # Default properties (no evolution) - all at midpoint
            self._size_norm = 0.5
            self._speed_norm = 0.5
            self._flee_norm = 0.5
            self._attack_norm = 0.5
        
        self.vx = random.uniform(-self.speed, self.speed)
        self.vy = random.uniform(-self.speed, self.speed)
        
        # Update image size if evolution enabled
        self._update_scaled_image()
    
    def _init_random_balanced(self):
        """Initialize with random values that sum to PROPERTY_BUDGET"""
        # Generate 4 random values
        values = [random.random() for _ in range(self.NUM_PROPERTIES)]
        # Normalize to sum to PROPERTY_BUDGET
        total = sum(values)
        scale = PROPERTY_BUDGET / total
        values = [v * scale for v in values]
        # Clamp each to 0-1 range and redistribute excess
        values = self._clamp_and_redistribute(values)
        
        self._size_norm, self._speed_norm, self._flee_norm, self._attack_norm = values
    
    def _inherit_balanced(self, parent):
        """Inherit properties with balanced mutation - if one goes up, others go down"""
        # Get parent's normalized values
        values = [
            parent._size_norm,
            parent._speed_norm,
            parent._flee_norm,
            parent._attack_norm
        ]
        
        # Pick a random property to mutate
        mutate_idx = random.randint(0, self.NUM_PROPERTIES - 1)
        mutation = random.uniform(-MUTATION_RATE, MUTATION_RATE)
        
        # Apply mutation to selected property
        values[mutate_idx] += mutation
        
        # Distribute the opposite change to other properties
        compensation = -mutation / (self.NUM_PROPERTIES - 1)
        for i in range(self.NUM_PROPERTIES):
            if i != mutate_idx:
                values[i] += compensation
        
        # Clamp and redistribute to ensure valid range
        values = self._clamp_and_redistribute(values)
        
        self._size_norm, self._speed_norm, self._flee_norm, self._attack_norm = values
    
    def _clamp_and_redistribute(self, values):
        """Clamp values to 0-1 and redistribute excess to maintain sum"""
        # Clamp and track excess
        for _ in range(10):  # Iterate to handle cascading clamps
            excess = 0
            clamped_count = 0
            
            for i in range(len(values)):
                if values[i] < 0:
                    excess += values[i]
                    values[i] = 0
                    clamped_count += 1
                elif values[i] > 1:
                    excess += values[i] - 1
                    values[i] = 1
                    clamped_count += 1
            
            if abs(excess) < 0.001 or clamped_count == len(values):
                break
            
            # Redistribute excess to non-clamped values
            unclamped = [i for i in range(len(values)) if 0 < values[i] < 1]
            if unclamped:
                share = excess / len(unclamped)
                for i in unclamped:
                    values[i] += share
        
        return values
    
    # Property getters that convert normalized values to actual ranges
    @property
    def size(self):
        return MIN_SIZE + self._size_norm * (MAX_SIZE - MIN_SIZE)
    
    @property
    def speed(self):
        return MIN_SPEED + self._speed_norm * (MAX_SPEED - MIN_SPEED)
    
    @property
    def flee_distance(self):
        return MIN_FLEE_DISTANCE + self._flee_norm * (MAX_FLEE_DISTANCE - MIN_FLEE_DISTANCE)
    
    @property
    def attack_distance(self):
        return MIN_ATTACK_DISTANCE + self._attack_norm * (MAX_ATTACK_DISTANCE - MIN_ATTACK_DISTANCE)
    
    def _mutate(self, value, min_val, max_val):
        """Mutate a value with some randomness (legacy, kept for compatibility)"""
        mutation = random.uniform(-MUTATION_RATE, MUTATION_RATE) * (max_val - min_val)
        new_value = value + mutation
        return max(min_val, min(max_val, new_value))
    
    def _update_scaled_image(self):
        """Scale the image based on entity size"""
        if self.base_image:
            size = int(self.size)
            self.scaled_image = pygame.transform.scale(self.base_image, (size, size))
        else:
            self.scaled_image = None
        
    def update(self, entities, screen_width, screen_height):
        # Find nearest threat and nearest prey
        nearest_threat = None
        nearest_threat_dist = float('inf')
        nearest_prey = None
        nearest_prey_dist = float('inf')
        
        threat_type = None
        prey_type = BEATS[self.entity_type]
        
        # Find what threatens us
        for t, beats in BEATS.items():
            if beats == self.entity_type:
                threat_type = t
                break
        
        for entity in entities:
            if entity is self:
                continue
            dist = self.distance_to(entity)
            
            # Check if it's a threat
            if entity.entity_type == threat_type and dist < nearest_threat_dist:
                nearest_threat = entity
                nearest_threat_dist = dist
            
            # Check if it's prey
            if entity.entity_type == prey_type and dist < nearest_prey_dist:
                nearest_prey = entity
                nearest_prey_dist = dist
        
        # Behavior: flee from threats, chase prey
        target_dx, target_dy = 0, 0
        
        # Soft collision with same type - calculate repulsion force
        repel_dx, repel_dy = 0, 0
        for entity in entities:
            if entity is self:
                continue
            if entity.entity_type == self.entity_type:
                dist = self.distance_to(entity)
                if dist < SAME_TYPE_REPEL_RADIUS and dist > 0:
                    # Calculate repulsion force (stronger when closer)
                    dx = self.x - entity.x
                    dy = self.y - entity.y
                    # Force increases as distance decreases
                    force = (SAME_TYPE_REPEL_RADIUS - dist) / SAME_TYPE_REPEL_RADIUS
                    force *= SAME_TYPE_REPEL_STRENGTH
                    repel_dx += (dx / dist) * force
                    repel_dy += (dy / dist) * force
        
        # Priority: flee if threat is close (using individual flee_distance)
        if nearest_threat and nearest_threat_dist < self.flee_distance:
            # Flee from threat
            dx = self.x - nearest_threat.x
            dy = self.y - nearest_threat.y
            dist = max(math.sqrt(dx*dx + dy*dy), 0.1)
            target_dx = (dx / dist) * self.speed * 1.5
            target_dy = (dy / dist) * self.speed * 1.5
        elif nearest_prey and nearest_prey_dist < self.attack_distance:
            # Chase prey (using individual attack_distance)
            dx = nearest_prey.x - self.x
            dy = nearest_prey.y - self.y
            dist = max(math.sqrt(dx*dx + dy*dy), 0.1)
            target_dx = (dx / dist) * self.speed
            target_dy = (dy / dist) * self.speed
        else:
            # Random wandering
            if random.random() < 0.02:
                self.vx = random.uniform(-self.speed, self.speed)
                self.vy = random.uniform(-self.speed, self.speed)
            target_dx = self.vx
            target_dy = self.vy
        
        # Smooth velocity change
        self.vx = self.vx * 0.9 + target_dx * 0.1
        self.vy = self.vy * 0.9 + target_dy * 0.1
        
        # Apply same-type repulsion force
        self.vx += repel_dx
        self.vy += repel_dy
        
        # Update position
        self.x += self.vx
        self.y += self.vy
        
        # Bounce off walls (using individual size)
        margin = int(self.size) // 2
        if self.x < margin:
            self.x = margin
            self.vx *= -1
        if self.x > screen_width - margin:
            self.x = screen_width - margin
            self.vx *= -1
        if self.y < margin:
            self.y = margin
            self.vy *= -1
        if self.y > screen_height - margin:
            self.y = screen_height - margin
            self.vy *= -1
    
    def distance_to(self, other):
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)
    
    def collides_with(self, other):
        # Use average of both entity sizes for collision
        collision_dist = (self.size + other.size) / 2
        return self.distance_to(other) < collision_dist
    
    def draw(self, screen):
        size = int(self.size)
        if self.scaled_image:
            rect = self.scaled_image.get_rect(center=(int(self.x), int(self.y)))
            screen.blit(self.scaled_image, rect)
        else:
            # Fallback to colored circle with individual size
            pygame.draw.circle(screen, TYPE_COLORS[self.entity_type], 
                             (int(self.x), int(self.y)), size // 2)
            pygame.draw.circle(screen, BLACK, 
                             (int(self.x), int(self.y)), size // 2, 2)
    
    def inherit_properties_from(self, parent):
        """Copy evolutionary properties from a parent (winner in collision)"""
        self._inherit_balanced(parent)
        self._update_scaled_image()


class Game:
    def __init__(self):
        # Dynamic screen dimensions
        self.screen_width = DEFAULT_SCREEN_WIDTH
        self.screen_height = DEFAULT_SCREEN_HEIGHT
        
        # Create resizable window
        self.screen = pygame.display.set_mode(
            (self.screen_width, self.screen_height), 
            pygame.RESIZABLE
        )
        pygame.display.set_caption("Rock Paper Scissors - Battle Royale")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 24)
        self.title_font = pygame.font.Font(None, 72)
        
        # Game area (leaving space for UI) - will be updated on resize
        self.update_layout()
        
        # Load images
        self.images = self.load_images()
        
        # Game state
        self.entities = []
        self.running = True
        self.paused = False
        self.game_over = False
        self.winner = None
        self.speed_multiplier = 1.0
        self.evolution_enabled = EVOLUTION_ENABLED  # Toggle for evolution
        self.initial_count = INITIAL_COUNT  # Adjustable initial count per type
        
        # Statistics
        self.conversions = {ROCK: 0, PAPER: 0, SCISSORS: 0}
        
        # Population history for graphing
        self.population_history = {ROCK: [], PAPER: [], SCISSORS: []}
        self.time_history = []
        self.frame_count = 0
        self.graphing_enabled = False  # Toggle for live graphing
        self.record_interval = 10  # Record population every N frames
        
        # Real-time graph window
        self.graph_window_open = False
        self.graph_fig = None
        self.graph_ax = None
        self.graph_lines = {}
        
        # Thread pool for parallel entity updates (fallback)
        self.thread_pool = ThreadPoolExecutor(max_workers=NUM_THREADS)
        self.entity_lock = threading.Lock()
        
        # GPU acceleration flag
        self.use_gpu = GPU_AVAILABLE
        
        # Buttons (will be created dynamically)
        self.buttons = []
        self.update_buttons()
        
        # Initialize game
        self.reset_game()
    
    def load_images(self):
        images = {}
        base_path = os.path.dirname(os.path.abspath(__file__))
        image_files = {
            ROCK: "images/boulder-clipart-transparent-background-rock-1-3961670665.png",
            PAPER: "images/Paper-Sheet-PNG-Transparent-Background-3062699109.png",
            SCISSORS: "images/scissors_PNG28-2679021845.png"
        }
        
        for entity_type, filename in image_files.items():
            try:
                path = os.path.join(base_path, filename)
                img = pygame.image.load(path).convert_alpha()
                # Store original image (scaling done per-entity for evolution)
                img = pygame.transform.scale(img, (MAX_SIZE, MAX_SIZE))  # Scale to max size
                images[entity_type] = img
            except Exception as e:
                print(f"Could not load image for {entity_type}: {e}")
                images[entity_type] = None
        
        return images
    
    def update_layout(self):
        """Update game area and UI positions based on current screen size"""
        self.game_area = pygame.Rect(0, 0, self.screen_width - UI_PANEL_WIDTH, self.screen_height)
    
    def update_buttons(self):
        """Recreate buttons with positions based on current screen size"""
        buttons = []
        button_x = self.screen_width - UI_PANEL_WIDTH + 10
        button_width = UI_PANEL_WIDTH - 20
        button_height = 35
        button_spacing = 40
        
        # Start buttons after the stats section (around y=250)
        start_y = 250
        y = start_y
        
        buttons.append({
            'rect': pygame.Rect(button_x, y, button_width, button_height),
            'text': 'Start/Restart',
            'action': 'restart'
        })
        y += button_spacing
        
        buttons.append({
            'rect': pygame.Rect(button_x, y, button_width, button_height),
            'text': 'Pause/Resume',
            'action': 'pause'
        })
        y += button_spacing
        
        buttons.append({
            'rect': pygame.Rect(button_x, y, button_width, button_height),
            'text': f'Speed: {self.speed_multiplier}x',
            'action': 'speed'
        })
        y += button_spacing
        
        buttons.append({
            'rect': pygame.Rect(button_x, y, button_width, button_height),
            'text': 'Add Rock',
            'action': 'add_rock'
        })
        y += button_spacing
        
        buttons.append({
            'rect': pygame.Rect(button_x, y, button_width, button_height),
            'text': 'Add Paper',
            'action': 'add_paper'
        })
        y += button_spacing
        
        buttons.append({
            'rect': pygame.Rect(button_x, y, button_width, button_height),
            'text': 'Add Scissors',
            'action': 'add_scissors'
        })
        y += button_spacing
        
        buttons.append({
            'rect': pygame.Rect(button_x, y, button_width, button_height),
            'text': 'Evolution: ON' if self.evolution_enabled else 'Evolution: OFF',
            'action': 'toggle_evolution'
        })
        y += button_spacing
        
        # Initial count adjustment buttons (smaller, side by side)
        half_width = button_width // 2 - 5
        buttons.append({
            'rect': pygame.Rect(button_x, y, half_width, button_height),
            'text': 'Count -',
            'action': 'count_down'
        })
        buttons.append({
            'rect': pygame.Rect(button_x + half_width + 10, y, half_width, button_height),
            'text': 'Count +',
            'action': 'count_up'
        })
        y += button_spacing
        
        # Graph toggle button
        if MATPLOTLIB_AVAILABLE:
            buttons.append({
                'rect': pygame.Rect(button_x, y, button_width, button_height),
                'text': 'Graph: ON' if self.graphing_enabled else 'Graph: OFF',
                'action': 'toggle_graph'
            })
            y += button_spacing
            
            buttons.append({
                'rect': pygame.Rect(button_x, y, button_width, button_height),
                'text': 'Open Graph' if not self.graph_window_open else 'Graph Open',
                'action': 'show_graph'
            })
        
        self.buttons = buttons
    
    def create_buttons(self):
        """Legacy method - redirects to update_buttons"""
        self.update_buttons()
        return self.buttons
    
    def reset_game(self):
        self.entities = []
        self.game_over = False
        self.winner = None
        self.paused = False
        self.conversions = {ROCK: 0, PAPER: 0, SCISSORS: 0}
        
        # Reset population history
        self.population_history = {ROCK: [], PAPER: [], SCISSORS: []}
        self.time_history = []
        self.frame_count = 0
        
        # Create initial entities
        for entity_type in [ROCK, PAPER, SCISSORS]:
            for _ in range(self.initial_count):
                self.spawn_entity(entity_type)
    
    def spawn_entity(self, entity_type, x=None, y=None, parent=None):
        if x is None:
            x = random.randint(ENTITY_SIZE, self.game_area.width - ENTITY_SIZE)
        if y is None:
            y = random.randint(ENTITY_SIZE, self.game_area.height - ENTITY_SIZE)
        
        entity = Entity(x, y, entity_type, self.images.get(entity_type), 
                       parent=parent, evolution_enabled=self.evolution_enabled)
        self.entities.append(entity)
    
    def count_entities(self):
        counts = {ROCK: 0, PAPER: 0, SCISSORS: 0}
        for entity in self.entities:
            counts[entity.entity_type] += 1
        return counts
    
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                # Handle window resize
                self.screen_width = max(MIN_SCREEN_WIDTH, event.w)
                self.screen_height = max(MIN_SCREEN_HEIGHT, event.h)
                self.screen = pygame.display.set_mode(
                    (self.screen_width, self.screen_height),
                    pygame.RESIZABLE
                )
                self.update_layout()
                self.update_buttons()
                # Clamp entities to new game area
                for entity in self.entities:
                    entity.x = max(entity.size/2, min(self.game_area.width - entity.size/2, entity.x))
                    entity.y = max(entity.size/2, min(self.game_area.height - entity.size/2, entity.y))
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    self.paused = not self.paused
                elif event.key == pygame.K_r:
                    self.reset_game()
                elif event.key == pygame.K_ESCAPE:
                    self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mouse_pos = pygame.mouse.get_pos()
                
                # Check button clicks
                for button in self.buttons:
                    if button['rect'].collidepoint(mouse_pos):
                        self.handle_button_click(button['action'])
                        break
                else:
                    # Click in game area to spawn entity
                    if self.game_area.collidepoint(mouse_pos):
                        # Left click: add random entity
                        if event.button == 1:
                            entity_type = random.choice([ROCK, PAPER, SCISSORS])
                            self.spawn_entity(entity_type, mouse_pos[0], mouse_pos[1])
    
    def handle_button_click(self, action):
        if action == 'restart':
            self.reset_game()
        elif action == 'pause':
            self.paused = not self.paused
        elif action == 'speed':
            self.speed_multiplier *= 2
            if self.speed_multiplier > 4:
                self.speed_multiplier = 0.5
            self.update_buttons()
        elif action == 'add_rock':
            self.spawn_entity(ROCK)
        elif action == 'add_paper':
            self.spawn_entity(PAPER)
        elif action == 'add_scissors':
            self.spawn_entity(SCISSORS)
        elif action == 'toggle_evolution':
            self.evolution_enabled = not self.evolution_enabled
            self.update_buttons()
            # Restart game with new setting
            self.reset_game()
        elif action == 'count_down':
            self.initial_count = max(1, self.initial_count - 5)
            self.reset_game()
        elif action == 'count_up':
            self.initial_count = min(500, self.initial_count + 5)
            self.reset_game()
        elif action == 'toggle_graph':
            self.graphing_enabled = not self.graphing_enabled
            self.update_buttons()
        elif action == 'show_graph':
            self.show_population_graph()
            self.update_buttons()
    
    def update_entity_batch(self, entities_batch, all_entities, width, height):
        """Update a batch of entities (called in thread)"""
        for entity in entities_batch:
            entity.update(all_entities, width, height)
    
    def gpu_update_entities(self):
        """GPU-accelerated entity position and velocity updates"""
        if len(self.entities) == 0:
            return
        
        n = len(self.entities)
        xp = cp if self.use_gpu else np
        
        # Extract entity data to arrays
        positions = xp.array([[e.x, e.y] for e in self.entities], dtype=xp.float32)
        velocities = xp.array([[e.vx, e.vy] for e in self.entities], dtype=xp.float32)
        speeds = xp.array([e.speed for e in self.entities], dtype=xp.float32)
        flee_distances = xp.array([e.flee_distance for e in self.entities], dtype=xp.float32)
        attack_distances = xp.array([e.attack_distance for e in self.entities], dtype=xp.float32)
        sizes = xp.array([e.size for e in self.entities], dtype=xp.float32)
        
        # Map entity types to integers: rock=0, paper=1, scissors=2
        type_map = {ROCK: 0, PAPER: 1, SCISSORS: 2}
        types = xp.array([type_map[e.entity_type] for e in self.entities], dtype=xp.int32)
        
        # Threat/prey relationships: rock(0)->scissors(2), paper(1)->rock(0), scissors(2)->paper(1)
        # prey[i] = what type i beats
        prey_types = xp.array([2, 0, 1], dtype=xp.int32)  # rock beats scissors, etc.
        threat_types = xp.array([1, 2, 0], dtype=xp.int32)  # paper beats rock, etc.
        
        # Compute pairwise distance matrix (n x n)
        # diff[i,j] = positions[j] - positions[i]
        diff = positions[xp.newaxis, :, :] - positions[:, xp.newaxis, :]  # (n, n, 2)
        dist_sq = xp.sum(diff ** 2, axis=2)  # (n, n)
        dist = xp.sqrt(dist_sq + 1e-10)  # Avoid division by zero
        
        # Direction vectors (normalized)
        direction = diff / dist[:, :, xp.newaxis]  # (n, n, 2)
        
        # Find nearest threat and prey for each entity
        entity_prey = prey_types[types]  # What each entity hunts
        entity_threat = threat_types[types]  # What threatens each entity
        
        # Create masks for prey and threat relationships
        is_prey = (types[xp.newaxis, :] == entity_prey[:, xp.newaxis])  # (n, n)
        is_threat = (types[xp.newaxis, :] == entity_threat[:, xp.newaxis])  # (n, n)
        is_same_type = (types[xp.newaxis, :] == types[:, xp.newaxis])  # (n, n)
        
        # Mask self-distances
        eye_mask = xp.eye(n, dtype=bool)
        dist_masked = xp.where(eye_mask, xp.inf, dist)
        
        # Find nearest threat
        threat_dist = xp.where(is_threat, dist_masked, xp.inf)
        nearest_threat_idx = xp.argmin(threat_dist, axis=1)
        nearest_threat_dist = threat_dist[xp.arange(n), nearest_threat_idx]
        
        # Find nearest prey
        prey_dist = xp.where(is_prey, dist_masked, xp.inf)
        nearest_prey_idx = xp.argmin(prey_dist, axis=1)
        nearest_prey_dist = prey_dist[xp.arange(n), nearest_prey_idx]
        
        # Calculate target velocities based on behavior
        target_vel = xp.zeros_like(velocities)
        
        # Flee behavior (when threat is within flee_distance)
        fleeing = nearest_threat_dist < flee_distances
        flee_dir = -direction[xp.arange(n), nearest_threat_idx]  # Away from threat
        target_vel = xp.where(
            fleeing[:, xp.newaxis],
            flee_dir * (speeds * 1.5)[:, xp.newaxis],
            target_vel
        )
        
        # Chase behavior (when not fleeing and prey is within attack_distance)
        chasing = (~fleeing) & (nearest_prey_dist < attack_distances)
        chase_dir = direction[xp.arange(n), nearest_prey_idx]  # Toward prey
        target_vel = xp.where(
            chasing[:, xp.newaxis],
            chase_dir * speeds[:, xp.newaxis],
            target_vel
        )
        
        # Wandering (when neither fleeing nor chasing) - keep current velocity with random changes
        wandering = (~fleeing) & (~chasing)
        # Random direction change for wandering entities (2% chance per frame)
        random_change = xp.array(np.random.random(n) < 0.02, dtype=bool)
        random_vel = xp.array(
            np.column_stack([
                np.random.uniform(-1, 1, n) * speeds.get() if self.use_gpu else speeds,
                np.random.uniform(-1, 1, n) * speeds.get() if self.use_gpu else speeds
            ]), dtype=xp.float32
        ) if self.use_gpu else np.column_stack([
            np.random.uniform(-1, 1, n) * speeds,
            np.random.uniform(-1, 1, n) * speeds
        ]).astype(np.float32)
        
        wander_vel = xp.where(
            (wandering & random_change)[:, xp.newaxis],
            random_vel,
            velocities
        )
        target_vel = xp.where(
            wandering[:, xp.newaxis],
            wander_vel,
            target_vel
        )
        
        # Same-type repulsion
        repel_mask = is_same_type & (~eye_mask) & (dist < SAME_TYPE_REPEL_RADIUS)
        repel_force = xp.where(dist > 0, (SAME_TYPE_REPEL_RADIUS - dist) / SAME_TYPE_REPEL_RADIUS, 0)
        repel_force = repel_force * SAME_TYPE_REPEL_STRENGTH
        repel_dir = -direction  # Away from same-type entity
        repel_contrib = xp.where(
            repel_mask[:, :, xp.newaxis],
            repel_dir * repel_force[:, :, xp.newaxis],
            0
        )
        repel_vel = xp.sum(repel_contrib, axis=1)  # Sum all repulsion forces
        
        # Smooth velocity update
        new_velocities = velocities * 0.9 + target_vel * 0.1 + repel_vel
        
        # Update positions
        new_positions = positions + new_velocities
        
        # Bounce off walls
        width = self.game_area.width
        height = self.game_area.height
        margins = sizes / 2
        
        # X bounds
        hit_left = new_positions[:, 0] < margins
        hit_right = new_positions[:, 0] > width - margins
        new_positions[:, 0] = xp.where(hit_left, margins, new_positions[:, 0])
        new_positions[:, 0] = xp.where(hit_right, width - margins, new_positions[:, 0])
        new_velocities[:, 0] = xp.where(hit_left | hit_right, -new_velocities[:, 0], new_velocities[:, 0])
        
        # Y bounds
        hit_top = new_positions[:, 1] < margins
        hit_bottom = new_positions[:, 1] > height - margins
        new_positions[:, 1] = xp.where(hit_top, margins, new_positions[:, 1])
        new_positions[:, 1] = xp.where(hit_bottom, height - margins, new_positions[:, 1])
        new_velocities[:, 1] = xp.where(hit_top | hit_bottom, -new_velocities[:, 1], new_velocities[:, 1])
        
        # Transfer back to CPU if using GPU
        if self.use_gpu:
            new_positions = cp.asnumpy(new_positions)
            new_velocities = cp.asnumpy(new_velocities)
        
        # Update entity objects
        for i, entity in enumerate(self.entities):
            entity.x = float(new_positions[i, 0])
            entity.y = float(new_positions[i, 1])
            entity.vx = float(new_velocities[i, 0])
            entity.vy = float(new_velocities[i, 1])
    
    def update(self):
        if self.paused or self.game_over:
            return
        
        # Update entities multiple times based on speed
        updates = max(1, int(self.speed_multiplier))
        for _ in range(updates):
            # Use GPU acceleration if available and enough entities
            if self.use_gpu and len(self.entities) > 20:
                try:
                    self.gpu_update_entities()
                except Exception as e:
                    # GPU failed at runtime, disable and fall back to CPU
                    print(f"GPU update failed: {type(e).__name__}, switching to CPU")
                    self.use_gpu = False
                    # Do CPU update for this frame
                    for entity in self.entities:
                        entity.update(self.entities, self.game_area.width, self.game_area.height)
            elif len(self.entities) > 50:
                # CPU parallel entity updates using thread pool
                batch_size = max(1, len(self.entities) // NUM_THREADS)
                batches = [
                    self.entities[i:i + batch_size] 
                    for i in range(0, len(self.entities), batch_size)
                ]
                
                # Submit all batches to thread pool
                futures = []
                for batch in batches:
                    future = self.thread_pool.submit(
                        self.update_entity_batch, 
                        batch, 
                        self.entities, 
                        self.game_area.width, 
                        self.game_area.height
                    )
                    futures.append(future)
                
                # Wait for all updates to complete
                for future in futures:
                    future.result()
            else:
                # Sequential update for small entity counts
                for entity in self.entities:
                    entity.update(self.entities, self.game_area.width, self.game_area.height)
            
            # Check collisions (must be sequential to avoid race conditions)
            self.check_collisions()
        
        # Record population for graphing
        self.frame_count += 1
        if self.graphing_enabled and self.frame_count % self.record_interval == 0:
            counts = self.count_entities()
            self.time_history.append(self.frame_count / FPS)  # Time in seconds
            for entity_type in [ROCK, PAPER, SCISSORS]:
                self.population_history[entity_type].append(counts[entity_type])
            
            # Update real-time graph (must be on main thread for matplotlib)
            if self.graph_window_open:
                self.update_realtime_graph()
        
        # Check for winner
        counts = self.count_entities()
        types_remaining = sum(1 for c in counts.values() if c > 0)
        
        if types_remaining == 1:
            self.game_over = True
            for entity_type, count in counts.items():
                if count > 0:
                    self.winner = entity_type
                    break
        elif types_remaining == 0:
            self.game_over = True
            self.winner = None
    
    def check_collisions(self):
        conversions = []
        
        for i, entity1 in enumerate(self.entities):
            for entity2 in self.entities[i+1:]:
                if entity1.collides_with(entity2):
                    # Determine winner
                    if BEATS[entity1.entity_type] == entity2.entity_type:
                        # Entity1 wins, convert entity2
                        conversions.append((entity2, entity1.entity_type, entity1))
                        self.conversions[entity1.entity_type] += 1
                    elif BEATS[entity2.entity_type] == entity1.entity_type:
                        # Entity2 wins, convert entity1
                        conversions.append((entity1, entity2.entity_type, entity2))
                        self.conversions[entity2.entity_type] += 1
                    # If same type, nothing happens
        
        # Apply conversions
        for entity, new_type, winner in conversions:
            entity.entity_type = new_type
            entity.base_image = self.images.get(new_type)
            # Inherit evolutionary properties from winner
            if self.evolution_enabled:
                entity.inherit_properties_from(winner)
            else:
                entity._update_scaled_image()
    
    def open_realtime_graph(self):
        """Open a real-time graph window"""
        if not MATPLOTLIB_AVAILABLE:
            print("matplotlib not available")
            return
        
        if self.graph_window_open:
            print("Graph window already open")
            return
        
        self.graph_window_open = True
        
        # Enable graphing automatically
        self.graphing_enabled = True
        self.update_buttons()
        
        # Create figure and axis
        plt.ion()  # Enable interactive mode
        self.graph_fig, self.graph_ax = plt.subplots(figsize=(8, 5))
        self.graph_fig.canvas.manager.set_window_title('Population Over Time')
        
        # Set up the plot
        colors = {
            ROCK: '#8B4513',      # Brown
            PAPER: '#DAA520',     # Golden rod (more visible than beige)
            SCISSORS: '#708090'   # Slate gray (more visible than silver)
        }
        
        # Initialize empty lines
        self.graph_lines = {}
        for entity_type in [ROCK, PAPER, SCISSORS]:
            line, = self.graph_ax.plot([], [], 
                                       label=entity_type.capitalize(),
                                       color=colors[entity_type],
                                       linewidth=2)
            self.graph_lines[entity_type] = line
        
        self.graph_ax.set_xlabel('Time (seconds)', fontsize=12)
        self.graph_ax.set_ylabel('Population', fontsize=12)
        self.graph_ax.set_title('Rock Paper Scissors - Real-time Population', fontsize=14)
        self.graph_ax.legend(loc='upper right')
        self.graph_ax.grid(True, alpha=0.3)
        self.graph_ax.set_xlim(0, 10)
        self.graph_ax.set_ylim(0, self.initial_count * 3 + 10)
        
        # Handle window close event
        def on_close(event):
            self.graph_window_open = False
            self.graph_fig = None
            self.graph_ax = None
            self.graph_lines = {}
        
        self.graph_fig.canvas.mpl_connect('close_event', on_close)
        
        plt.tight_layout()
        plt.show(block=False)
    
    def update_realtime_graph(self):
        """Update the real-time graph with current data"""
        if not self.graph_window_open or self.graph_fig is None:
            return
        
        if not self.time_history:
            return
        
        try:
            # Update line data
            for entity_type in [ROCK, PAPER, SCISSORS]:
                if entity_type in self.graph_lines:
                    self.graph_lines[entity_type].set_data(
                        self.time_history, 
                        self.population_history[entity_type]
                    )
            
            # Adjust x-axis limits
            max_time = max(self.time_history) if self.time_history else 10
            self.graph_ax.set_xlim(0, max(10, max_time + 1))
            
            # Adjust y-axis limits
            max_pop = max(
                max(self.population_history[ROCK]) if self.population_history[ROCK] else 0,
                max(self.population_history[PAPER]) if self.population_history[PAPER] else 0,
                max(self.population_history[SCISSORS]) if self.population_history[SCISSORS] else 0
            )
            self.graph_ax.set_ylim(0, max(10, max_pop + 5))
            
            # Redraw - use pause to process events
            self.graph_fig.canvas.draw_idle()
            plt.pause(0.001)  # Small pause to process matplotlib events
        except Exception as e:
            # Graph window might have been closed
            self.graph_window_open = False
    
    def show_population_graph(self):
        """Open real-time graph window or show static graph"""
        if not MATPLOTLIB_AVAILABLE:
            print("matplotlib not available")
            return
        
        # Open real-time graph
        self.open_realtime_graph()
    
    def draw(self):
        # Clear screen
        self.screen.fill(DARK_GRAY)
        
        # Draw game area background
        pygame.draw.rect(self.screen, (30, 30, 50), self.game_area)
        pygame.draw.rect(self.screen, WHITE, self.game_area, 2)
        
        # Draw entities
        for entity in self.entities:
            entity.draw(self.screen)
        
        # Draw UI panel
        self.draw_ui()
        
        # Draw game over screen
        if self.game_over:
            self.draw_game_over()
        
        # Draw pause indicator
        if self.paused and not self.game_over:
            pause_text = self.title_font.render("PAUSED", True, YELLOW)
            rect = pause_text.get_rect(center=(self.game_area.width // 2, self.game_area.height // 2))
            # Draw background
            bg_rect = rect.inflate(40, 20)
            pygame.draw.rect(self.screen, (0, 0, 0, 128), bg_rect)
            self.screen.blit(pause_text, rect)
        
        pygame.display.flip()
    
    def draw_ui(self):
        panel_x = self.game_area.width + 10
        
        # Title
        title = self.font.render("RPS Battle Royale", True, WHITE)
        self.screen.blit(title, (panel_x, 20))
        
        # Counts
        counts = self.count_entities()
        y = 70
        
        for entity_type, count in counts.items():
            # Draw icon
            if self.images.get(entity_type):
                icon = pygame.transform.scale(self.images[entity_type], (30, 30))
                self.screen.blit(icon, (panel_x, y))
            else:
                pygame.draw.circle(self.screen, TYPE_COLORS[entity_type], 
                                 (panel_x + 15, y + 15), 15)
            
            # Draw count
            text = self.font.render(f": {count}", True, WHITE)
            self.screen.blit(text, (panel_x + 40, y))
            
            # Draw conversion count
            conv_text = self.small_font.render(f"(+{self.conversions[entity_type]})", True, GREEN)
            self.screen.blit(conv_text, (panel_x + 100, y + 5))
            
            y += 50
        
        # Total
        total = sum(counts.values())
        total_text = self.font.render(f"Total: {total}", True, WHITE)
        self.screen.blit(total_text, (panel_x, y + 10))
        
        # Draw initial count display
        count_text = self.small_font.render(f"Initial: {self.initial_count} per type", True, WHITE)
        self.screen.blit(count_text, (panel_x, y + 45))
        
        # Draw buttons
        for button in self.buttons:
            color = GRAY if button['rect'].collidepoint(pygame.mouse.get_pos()) else DARK_GRAY
            pygame.draw.rect(self.screen, color, button['rect'])
            pygame.draw.rect(self.screen, WHITE, button['rect'], 2)
            
            text = self.small_font.render(button['text'], True, WHITE)
            text_rect = text.get_rect(center=button['rect'].center)
            self.screen.blit(text, text_rect)
        
        # Instructions at the bottom of the screen
        instructions = [
            "SPACE: Pause | R: Restart | Click: Add | ESC: Quit"
        ]
        
        y = self.screen_height - 30
        for line in instructions:
            text = self.small_font.render(line, True, WHITE)
            self.screen.blit(text, (panel_x, y))
    
    def draw_game_over(self):
        # Semi-transparent overlay
        overlay = pygame.Surface((self.game_area.width, self.game_area.height))
        overlay.fill((0, 0, 0))
        overlay.set_alpha(180)
        self.screen.blit(overlay, (0, 0))
        
        # Winner text
        if self.winner:
            winner_text = self.title_font.render(f"{self.winner.upper()} WINS!", True, YELLOW)
        else:
            winner_text = self.title_font.render("DRAW!", True, YELLOW)
        
        rect = winner_text.get_rect(center=(self.game_area.width // 2, self.game_area.height // 2 - 50))
        self.screen.blit(winner_text, rect)
        
        # Winner icon
        if self.winner and self.images.get(self.winner):
            icon = pygame.transform.scale(self.images[self.winner], (100, 100))
            icon_rect = icon.get_rect(center=(self.game_area.width // 2, self.game_area.height // 2 + 50))
            self.screen.blit(icon, icon_rect)
        
        # Restart instruction
        restart_text = self.font.render("Press R or click 'Start/Restart' to play again", True, WHITE)
        rect = restart_text.get_rect(center=(self.game_area.width // 2, self.game_area.height // 2 + 150))
        self.screen.blit(restart_text, rect)
    
    def run(self):
        try:
            while self.running:
                self.handle_events()
                self.update()
                self.draw()
                self.clock.tick(FPS)
        finally:
            # Cleanup thread pool
            self.thread_pool.shutdown(wait=False)
            pygame.quit()


if __name__ == "__main__":
    game = Game()
    game.run()
