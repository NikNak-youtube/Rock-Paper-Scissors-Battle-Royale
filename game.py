"""
Game class for Rock Paper Scissors Battle Royale
"""

import pygame
import random
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import numpy as np

from config import (
    GPU_AVAILABLE, MATPLOTLIB_AVAILABLE, cp, plt,
    NUM_THREADS, DEFAULT_SCREEN_WIDTH, DEFAULT_SCREEN_HEIGHT,
    MIN_SCREEN_WIDTH, MIN_SCREEN_HEIGHT, UI_PANEL_WIDTH, FPS,
    WHITE, BLACK, GRAY, DARK_GRAY, GREEN, YELLOW,
    ENTITY_SIZE, INITIAL_COUNT, MAX_ENTITIES, EVOLUTION_ENABLED,
    EDGE_WRAP, RECORDING_ENABLED, RECORDING_FOLDER,
    MAX_SIZE, MAX_FLEE_DISTANCE, MAX_ATTACK_DISTANCE,
    SAME_TYPE_REPEL_RADIUS, SAME_TYPE_REPEL_STRENGTH,
    SPATIAL_GRID_CELL_SIZE, SHARED_CALC_ENABLED, SHARED_CALC_RADIUS,
    GROWTH_ENABLED, TINT_ENABLED,
    ROCK, PAPER, SCISSORS, BEATS, TYPE_COLORS
)
from entity import Entity


class SpatialGrid:
    """Uniform spatial hash grid for fast neighbor queries.

    Cells are keyed by (col, row) where col = floor(x / cell_size). Empty
    cells are absent from the dict so sparse worlds stay cheap.
    """

    def __init__(self, cell_size):
        self.cell_size = cell_size
        self.cells = {}

    def build(self, entities):
        """Re-populate the grid from scratch with the given entities."""
        cells = {}
        cs = self.cell_size
        for e in entities:
            key = (int(e.x // cs), int(e.y // cs))
            bucket = cells.get(key)
            if bucket is None:
                cells[key] = [e]
            else:
                bucket.append(e)
        self.cells = cells

    def query_radius(self, x, y, radius):
        """Return entities in cells overlapping the bounding box of the radius.

        May include entities slightly outside `radius` — the caller is expected
        to do an exact distance check on the candidates that matter.
        """
        cs = self.cell_size
        cell_radius = int(radius / cs) + 1
        center_col = int(x // cs)
        center_row = int(y // cs)
        cells = self.cells
        result = []
        for col in range(center_col - cell_radius, center_col + cell_radius + 1):
            for row in range(center_row - cell_radius, center_row + cell_radius + 1):
                bucket = cells.get((col, row))
                if bucket is not None:
                    result.extend(bucket)
        return result


class Game:
    """Main game class that handles the simulation."""
    
    def __init__(self):
        # Initialize pygame
        pygame.init()
        
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
        
        # Edge wrapping
        self.edge_wrap = EDGE_WRAP  # Toggle between wrap and bounce
        
        # Recording settings
        self.recording_enabled = RECORDING_ENABLED  # Toggle for frame recording
        self.recording_folder = None  # Will be set when recording starts
        self.recording_frame = 0  # Frame counter for recorded files
        
        # Statistics
        self.conversions = {ROCK: 0, PAPER: 0, SCISSORS: 0}

        # Per-frame cached counts (invalidated whenever entities mutate).
        self._cached_counts = None
        
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

        # Spatial hash grid — rebuilt each frame to accelerate neighbor lookups
        # and collision pair tests. Cell size is a tradeoff between cells-scanned
        # per query and entities-per-cell.
        self.spatial_grid = SpatialGrid(SPATIAL_GRID_CELL_SIZE)

        # Per-frame neighbor query radius (max of any entity's flee/attack range).
        # Recomputed lazily when entity properties or config change.
        self._neighbor_query_radius = max(
            MAX_FLEE_DISTANCE, MAX_ATTACK_DISTANCE, SAME_TYPE_REPEL_RADIUS
        )

        # Shared distance calculation (cluster scan reuse). Toggleable in UI.
        self.shared_calc_enabled = SHARED_CALC_ENABLED
        self._share_radius_sq = SHARED_CALC_RADIUS * SHARED_CALC_RADIUS

        # Monotonic counter that bumps every entity-update sub-iteration so
        # the per-tick neighbor cache invalidates between sub-iterations.
        self._update_tick = 0

        # Post-conversion growth (newly converted entities start small and
        # grow over time). Toggleable in UI.
        self.growth_enabled = GROWTH_ENABLED

        # RGB lineage tint. Genome is always inherited so toggling off and
        # back on still shows the family colors that drifted in between.
        self.tint_enabled = TINT_ENABLED

        # GPU acceleration flag
        self.use_gpu = GPU_AVAILABLE
        
        # Buttons (will be created dynamically)
        self.buttons = []
        self.update_buttons()
        
        # Initialize game
        self.reset_game()
    
    def load_images(self):
        """Load entity images from disk."""
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
        button_height = 28
        button_spacing = 31
        
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
        
        # Initial count adjustment buttons (smaller, side by side).
        # Top row: ±5; bottom row: ±100 for fast scaling toward MAX_ENTITIES.
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

        buttons.append({
            'rect': pygame.Rect(button_x, y, half_width, button_height),
            'text': 'Count --',
            'action': 'count_down_big'
        })
        buttons.append({
            'rect': pygame.Rect(button_x + half_width + 10, y, half_width, button_height),
            'text': 'Count ++',
            'action': 'count_up_big'
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
            y += button_spacing
        
        # Edge wrap toggle
        buttons.append({
            'rect': pygame.Rect(button_x, y, button_width, button_height),
            'text': 'Edges: Wrap' if self.edge_wrap else 'Edges: Bounce',
            'action': 'toggle_wrap'
        })
        y += button_spacing

        # Shared distance calculation toggle
        buttons.append({
            'rect': pygame.Rect(button_x, y, button_width, button_height),
            'text': 'Share Calc: ON' if self.shared_calc_enabled else 'Share Calc: OFF',
            'action': 'toggle_shared_calc'
        })
        y += button_spacing

        # Growth toggle
        buttons.append({
            'rect': pygame.Rect(button_x, y, button_width, button_height),
            'text': 'Growth: ON' if self.growth_enabled else 'Growth: OFF',
            'action': 'toggle_growth'
        })
        y += button_spacing

        # Tint toggle
        buttons.append({
            'rect': pygame.Rect(button_x, y, button_width, button_height),
            'text': 'Tint: ON' if self.tint_enabled else 'Tint: OFF',
            'action': 'toggle_tint'
        })
        y += button_spacing

        # Recording toggle
        buttons.append({
            'rect': pygame.Rect(button_x, y, button_width, button_height),
            'text': 'REC ●' if self.recording_enabled else 'Record: OFF',
            'action': 'toggle_recording'
        })
        
        self.buttons = buttons
    
    def reset_game(self):
        """Reset the game to initial state."""
        self.entities = []
        self.game_over = False
        self.winner = None
        self.paused = False
        self.conversions = {ROCK: 0, PAPER: 0, SCISSORS: 0}
        self._cached_counts = None
        
        # Reset population history
        self.population_history = {ROCK: [], PAPER: [], SCISSORS: []}
        self.time_history = []
        self.frame_count = 0
        
        # Create initial entities
        for entity_type in [ROCK, PAPER, SCISSORS]:
            for _ in range(self.initial_count):
                self.spawn_entity(entity_type)
    
    def spawn_entity(self, entity_type, x=None, y=None, parent=None):
        """Spawn a new entity of the given type."""
        if x is None:
            x = random.randint(ENTITY_SIZE, self.game_area.width - ENTITY_SIZE)
        if y is None:
            y = random.randint(ENTITY_SIZE, self.game_area.height - ENTITY_SIZE)
        
        entity = Entity(
            x, y, entity_type, self.images.get(entity_type),
            parent=parent,
            evolution_enabled=self.evolution_enabled,
            growth_enabled=self.growth_enabled,
            current_frame=self.frame_count,
            tint_enabled=self.tint_enabled,
        )
        self.entities.append(entity)
    
    def count_entities(self):
        """Count entities of each type. Cached within a frame."""
        if self._cached_counts is not None:
            return self._cached_counts
        counts = {ROCK: 0, PAPER: 0, SCISSORS: 0}
        for entity in self.entities:
            counts[entity.entity_type] += 1
        self._cached_counts = counts
        return counts
    
    def handle_events(self):
        """Handle pygame events."""
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
        """Handle button click actions."""
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
            self.initial_count = min(MAX_ENTITIES // 3, self.initial_count + 5)
            self.reset_game()
        elif action == 'count_down_big':
            self.initial_count = max(1, self.initial_count - 100)
            self.reset_game()
        elif action == 'count_up_big':
            self.initial_count = min(MAX_ENTITIES // 3, self.initial_count + 100)
            self.reset_game()
        elif action == 'toggle_graph':
            self.graphing_enabled = not self.graphing_enabled
            self.update_buttons()
        elif action == 'show_graph':
            self.show_population_graph()
            self.update_buttons()
        elif action == 'toggle_wrap':
            self.edge_wrap = not self.edge_wrap
            self.update_buttons()
        elif action == 'toggle_shared_calc':
            self.shared_calc_enabled = not self.shared_calc_enabled
            self.update_buttons()
        elif action == 'toggle_growth':
            self.growth_enabled = not self.growth_enabled
            # Apply immediately to live entities so the toggle is visible.
            for entity in self.entities:
                entity.reset_size_state(self.growth_enabled, self.frame_count)
            self.update_buttons()
        elif action == 'toggle_tint':
            self.tint_enabled = not self.tint_enabled
            for entity in self.entities:
                entity.set_tint_enabled(self.tint_enabled)
            self.update_buttons()
        elif action == 'toggle_recording':
            self.recording_enabled = not self.recording_enabled
            if self.recording_enabled:
                self.start_recording()
            else:
                self.stop_recording()
            self.update_buttons()
    
    def start_recording(self):
        """Create a timestamped folder for recording frames"""
        base_path = os.path.dirname(os.path.abspath(__file__))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.recording_folder = os.path.join(base_path, RECORDING_FOLDER, timestamp)
        os.makedirs(self.recording_folder, exist_ok=True)
        self.recording_frame = 0
        print(f"Recording started: {self.recording_folder}")
        print(f"To create video: ffmpeg -framerate {FPS} -i {self.recording_folder}/frame_%06d.png -c:v libx264 -pix_fmt yuv420p output.mp4")
    
    def stop_recording(self):
        """Stop recording and print ffmpeg command"""
        if self.recording_folder:
            print(f"Recording stopped. {self.recording_frame} frames saved.")
            print(f"Create video with: ffmpeg -framerate {FPS} -i {self.recording_folder}/frame_%06d.png -c:v libx264 -pix_fmt yuv420p output.mp4")
        self.recording_folder = None
        self.recording_frame = 0
    
    def save_frame(self):
        """Save current frame as PNG"""
        if self.recording_enabled and self.recording_folder:
            filename = os.path.join(self.recording_folder, f"frame_{self.recording_frame:06d}.png")
            pygame.image.save(self.screen, filename)
            self.recording_frame += 1
    
    def update_entity_batch(self, entities_batch, grid, query_radius, width, height,
                            edge_wrap, tick, share_radius_sq):
        """Update a batch of entities (called in thread).

        Each entity queries the shared spatial grid for its own neighbor list.
        The grid is read-only during this phase, so concurrent reads are safe.
        """
        for entity in entities_batch:
            neighbors = grid.query_radius(entity.x, entity.y, query_radius)
            entity.update(neighbors, width, height, edge_wrap,
                          tick=tick, share_radius_sq=share_radius_sq)
    
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
        
        # Handle edges (wrap or bounce)
        width = self.game_area.width
        height = self.game_area.height
        margins = sizes / 2
        
        if self.edge_wrap:
            # Wrap around edges
            # X wrapping
            wrap_left = new_positions[:, 0] < -margins
            wrap_right = new_positions[:, 0] > width + margins
            new_positions[:, 0] = xp.where(wrap_left, width + margins, new_positions[:, 0])
            new_positions[:, 0] = xp.where(wrap_right, -margins, new_positions[:, 0])
            
            # Y wrapping
            wrap_top = new_positions[:, 1] < -margins
            wrap_bottom = new_positions[:, 1] > height + margins
            new_positions[:, 1] = xp.where(wrap_top, height + margins, new_positions[:, 1])
            new_positions[:, 1] = xp.where(wrap_bottom, -margins, new_positions[:, 1])
        else:
            # Bounce off walls
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
        """Update game state."""
        if self.paused or self.game_over:
            return

        # Invalidate per-frame caches.
        self._cached_counts = None
        
        # Update entities multiple times based on speed
        updates = max(1, int(self.speed_multiplier))
        width = self.game_area.width
        height = self.game_area.height
        grid = self.spatial_grid
        query_radius = self._neighbor_query_radius
        share_radius_sq = self._share_radius_sq if self.shared_calc_enabled else 0.0

        for _ in range(updates):
            # Bump tick so cached neighbor scans from prior sub-iterations
            # (or earlier frames) are recognized as stale.
            self._update_tick += 1
            tick = self._update_tick

            # Use GPU acceleration if available and enough entities.
            # GPU path is fully vectorized O(n²); spatial grid + cluster
            # sharing don't apply there, but still pay off for collision
            # detection below.
            if self.use_gpu and len(self.entities) > 20:
                try:
                    self.gpu_update_entities()
                except Exception as e:
                    # GPU failed at runtime, disable and fall back to CPU
                    print(f"GPU update failed: {type(e).__name__}, switching to CPU")
                    self.use_gpu = False
                    grid.build(self.entities)
                    for entity in self.entities:
                        neighbors = grid.query_radius(entity.x, entity.y, query_radius)
                        entity.update(neighbors, width, height, self.edge_wrap,
                                      tick=tick, share_radius_sq=share_radius_sq)
            elif len(self.entities) > 50:
                # CPU parallel updates: build grid once, threads query it.
                grid.build(self.entities)
                batch_size = max(1, len(self.entities) // NUM_THREADS)
                batches = [
                    self.entities[i:i + batch_size]
                    for i in range(0, len(self.entities), batch_size)
                ]

                futures = [
                    self.thread_pool.submit(
                        self.update_entity_batch,
                        batch, grid, query_radius, width, height,
                        self.edge_wrap, tick, share_radius_sq
                    )
                    for batch in batches
                ]
                for future in futures:
                    future.result()
            else:
                # Sequential update for small entity counts.
                # For very small N, the grid overhead is comparable to a direct
                # pass, but using it keeps the entity API consistent.
                grid.build(self.entities)
                for entity in self.entities:
                    neighbors = grid.query_radius(entity.x, entity.y, query_radius)
                    entity.update(neighbors, width, height, self.edge_wrap,
                                  tick=tick, share_radius_sq=share_radius_sq)

            # Rebuild grid against post-update positions so collision queries
            # see entities in their current cells.
            grid.build(self.entities)
            self.check_collisions()
        
        # Apply post-conversion growth. Per-frame rather than per-sub-iteration
        # so growth speed is tied to wall-clock seconds, not speed_multiplier.
        # Hot path: try_grow short-circuits on a single attribute compare for
        # fully-grown entities, so this is cheap even at large N.
        if self.growth_enabled:
            cf = self.frame_count
            for entity in self.entities:
                if entity.try_grow(cf):
                    entity._update_scaled_image()

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
        """Check and handle collisions between entities using the spatial grid."""
        conversions = []
        grid = self.spatial_grid
        # Max possible center-to-center collision distance is MAX_SIZE
        # (sum of two MAX_SIZE radii / 2 = MAX_SIZE).
        collision_query_radius = MAX_SIZE

        for entity1 in self.entities:
            e1_id = id(entity1)
            e1_type = entity1.entity_type
            e1_size = entity1.size
            x1 = entity1.x
            y1 = entity1.y
            beats_e1 = BEATS[e1_type]

            for entity2 in grid.query_radius(x1, y1, collision_query_radius):
                # Order pairs by id to process each pair exactly once.
                if id(entity2) <= e1_id:
                    continue
                e2_type = entity2.entity_type
                if e1_type == e2_type:
                    continue  # Same type — no collision outcome to compute

                dx = x1 - entity2.x
                dy = y1 - entity2.y
                collision_dist = (e1_size + entity2.size) * 0.5
                if dx * dx + dy * dy >= collision_dist * collision_dist:
                    continue

                if beats_e1 == e2_type:
                    conversions.append((entity2, e1_type, entity1))
                    self.conversions[e1_type] += 1
                else:
                    # entity2's type beats entity1 (the only remaining case
                    # since same-type was filtered above).
                    conversions.append((entity1, e2_type, entity2))
                    self.conversions[e2_type] += 1

        # Apply conversions
        growth_on = self.growth_enabled
        cf = self.frame_count
        for entity, new_type, winner in conversions:
            entity.entity_type = new_type
            entity.base_image = self.images.get(new_type)
            if self.evolution_enabled:
                entity.inherit_properties_from(winner)
            # Always inherit tint genome so the lineage trail survives
            # toggling tint render off and on.
            entity.inherit_tint_from(winner)
            # reset_size_state handles both growth-on (start small, grow up)
            # and growth-off (snap to evolved size) and re-scales the image
            # (which also re-applies the tint when render is enabled).
            entity.reset_size_state(growth_on, cf)
    
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
        """Draw the game."""
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
        """Draw the UI panel."""
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
        """Draw the game over screen."""
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
        """Main game loop."""
        try:
            while self.running:
                self.handle_events()
                self.update()
                self.draw()
                
                # Save frame if recording
                if self.recording_enabled:
                    self.save_frame()
                
                self.clock.tick(FPS)
        finally:
            # Stop recording if active
            if self.recording_enabled:
                self.stop_recording()
            # Cleanup thread pool
            self.thread_pool.shutdown(wait=False)
            pygame.quit()
