import pygame
import random
import math
import os

# Initialize pygame
pygame.init()

# Screen settings
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
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
    def __init__(self, x, y, entity_type, image=None, parent=None, evolution_enabled=True):
        self.x = x
        self.y = y
        self.entity_type = entity_type
        self.base_image = image  # Store original image
        self.image = image
        self.target = None
        self.flee_from = None
        
        # Evolutionary properties
        if evolution_enabled and parent:
            # Inherit from parent with mutation
            self.size = self._mutate(parent.size, MIN_SIZE, MAX_SIZE)
            self.speed = self._mutate(parent.speed, MIN_SPEED, MAX_SPEED)
            self.flee_distance = self._mutate(parent.flee_distance, MIN_FLEE_DISTANCE, MAX_FLEE_DISTANCE)
            self.attack_distance = self._mutate(parent.attack_distance, MIN_ATTACK_DISTANCE, MAX_ATTACK_DISTANCE)
        elif evolution_enabled:
            # Random initial properties
            self.size = random.uniform(MIN_SIZE, MAX_SIZE)
            self.speed = random.uniform(MIN_SPEED, MAX_SPEED)
            self.flee_distance = random.uniform(MIN_FLEE_DISTANCE, MAX_FLEE_DISTANCE)
            self.attack_distance = random.uniform(MIN_ATTACK_DISTANCE, MAX_ATTACK_DISTANCE)
        else:
            # Default properties (no evolution)
            self.size = ENTITY_SIZE
            self.speed = ENTITY_SPEED
            self.flee_distance = 150
            self.attack_distance = float('inf')
        
        self.vx = random.uniform(-self.speed, self.speed)
        self.vy = random.uniform(-self.speed, self.speed)
        
        # Update image size if evolution enabled
        self._update_scaled_image()
    
    def _mutate(self, value, min_val, max_val):
        """Mutate a value with some randomness"""
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
        self.size = self._mutate(parent.size, MIN_SIZE, MAX_SIZE)
        self.speed = self._mutate(parent.speed, MIN_SPEED, MAX_SPEED)
        self.flee_distance = self._mutate(parent.flee_distance, MIN_FLEE_DISTANCE, MAX_FLEE_DISTANCE)
        self.attack_distance = self._mutate(parent.attack_distance, MIN_ATTACK_DISTANCE, MAX_ATTACK_DISTANCE)
        self._update_scaled_image()


class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Rock Paper Scissors - Battle Royale")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 24)
        self.title_font = pygame.font.Font(None, 72)
        
        # Game area (leaving space for UI)
        self.game_area = pygame.Rect(0, 0, SCREEN_WIDTH - 200, SCREEN_HEIGHT)
        
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
        
        # Statistics
        self.conversions = {ROCK: 0, PAPER: 0, SCISSORS: 0}
        
        # Buttons
        self.buttons = self.create_buttons()
        
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
    
    def create_buttons(self):
        buttons = []
        button_x = SCREEN_WIDTH - 180
        button_width = 160
        button_height = 40
        
        buttons.append({
            'rect': pygame.Rect(button_x, 300, button_width, button_height),
            'text': 'Start/Restart',
            'action': 'restart'
        })
        buttons.append({
            'rect': pygame.Rect(button_x, 350, button_width, button_height),
            'text': 'Pause/Resume',
            'action': 'pause'
        })
        buttons.append({
            'rect': pygame.Rect(button_x, 400, button_width, button_height),
            'text': 'Speed: 1x',
            'action': 'speed'
        })
        buttons.append({
            'rect': pygame.Rect(button_x, 450, button_width, button_height),
            'text': 'Add Rock',
            'action': 'add_rock'
        })
        buttons.append({
            'rect': pygame.Rect(button_x, 500, button_width, button_height),
            'text': 'Add Paper',
            'action': 'add_paper'
        })
        buttons.append({
            'rect': pygame.Rect(button_x, 550, button_width, button_height),
            'text': 'Add Scissors',
            'action': 'add_scissors'
        })
        buttons.append({
            'rect': pygame.Rect(button_x, 600, button_width, button_height),
            'text': 'Evolution: ON' if EVOLUTION_ENABLED else 'Evolution: OFF',
            'action': 'toggle_evolution'
        })
        
        return buttons
    
    def reset_game(self):
        self.entities = []
        self.game_over = False
        self.winner = None
        self.paused = False
        self.conversions = {ROCK: 0, PAPER: 0, SCISSORS: 0}
        
        # Create initial entities
        for entity_type in [ROCK, PAPER, SCISSORS]:
            for _ in range(INITIAL_COUNT):
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
            # Update button text
            for button in self.buttons:
                if button['action'] == 'speed':
                    button['text'] = f'Speed: {self.speed_multiplier}x'
        elif action == 'add_rock':
            self.spawn_entity(ROCK)
        elif action == 'add_paper':
            self.spawn_entity(PAPER)
        elif action == 'add_scissors':
            self.spawn_entity(SCISSORS)
        elif action == 'toggle_evolution':
            self.evolution_enabled = not self.evolution_enabled
            # Update button text
            for button in self.buttons:
                if button['action'] == 'toggle_evolution':
                    button['text'] = 'Evolution: ON' if self.evolution_enabled else 'Evolution: OFF'
            # Restart game with new setting
            self.reset_game()
    
    def update(self):
        if self.paused or self.game_over:
            return
        
        # Update entities multiple times based on speed
        updates = max(1, int(self.speed_multiplier))
        for _ in range(updates):
            # Update all entities
            for entity in self.entities:
                entity.update(self.entities, self.game_area.width, self.game_area.height)
            
            # Check collisions
            self.check_collisions()
        
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
        
        # Draw buttons
        for button in self.buttons:
            color = GRAY if button['rect'].collidepoint(pygame.mouse.get_pos()) else DARK_GRAY
            pygame.draw.rect(self.screen, color, button['rect'])
            pygame.draw.rect(self.screen, WHITE, button['rect'], 2)
            
            text = self.small_font.render(button['text'], True, WHITE)
            text_rect = text.get_rect(center=button['rect'].center)
            self.screen.blit(text, text_rect)
        
        # Instructions
        instructions = [
            "Controls:",
            "SPACE - Pause/Resume",
            "R - Restart",
            "Click - Add random entity",
            "ESC - Quit"
        ]
        
        y = 620
        for line in instructions:
            text = self.small_font.render(line, True, WHITE)
            self.screen.blit(text, (panel_x, y))
            y += 25
    
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
        while self.running:
            self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(FPS)
        
        pygame.quit()


if __name__ == "__main__":
    game = Game()
    game.run()
