"""
Entity class for Rock Paper Scissors Battle Royale
"""

import pygame
import random
import math

from config import (
    BEATS, BEATEN_BY, TYPE_COLORS, MUTATION_RATE, PROPERTY_BUDGET,
    MIN_SIZE, MAX_SIZE, MIN_SPEED, MAX_SPEED,
    MIN_FLEE_DISTANCE, MAX_FLEE_DISTANCE,
    MIN_ATTACK_DISTANCE, MAX_ATTACK_DISTANCE,
    SAME_TYPE_REPEL_RADIUS, SAME_TYPE_REPEL_STRENGTH,
    GROWTH_CHANCE, GROWTH_INTERVAL_FRAMES, GROWTH_INCREMENT,
    GROWTH_START_SIZE,
    TINT_MUTATION, TINT_INIT_MIN, TINT_INIT_MAX,
    MIN_COMM_RADIUS, MAX_COMM_RADIUS,
    COMM_CHANCE_MIN, COMM_CHANCE_MAX, COMM_MUTATION,
    BLACK
)

# Precompute squared repulsion radius
_REPEL_RADIUS_SQ = SAME_TYPE_REPEL_RADIUS * SAME_TYPE_REPEL_RADIUS


class Entity:
    """Represents a rock, paper, or scissors entity in the simulation."""

    # Property count for balanced distribution
    NUM_PROPERTIES = 4

    # Shared cache for scaled images keyed by (id(base_image), int_size).
    # pygame.transform.scale is expensive; entities sharing the same source
    # image and size pixel-bucket reuse the same surface.
    _scaled_image_cache = {}
    
    def __init__(self, x, y, entity_type, image=None, parent=None,
                 evolution_enabled=True, growth_enabled=False, current_frame=0,
                 tint_enabled=True):
        self.x = x
        self.y = y
        self.entity_type = entity_type
        self.base_image = image  # Store original image
        self.image = image
        self.target = None
        self.flee_from = None

        # Shared neighbor-scan cache. Tick is the update-tick at which
        # _cache_data was populated; mismatched tick means stale and ignored.
        self._cache_tick = -1
        self._cache_data = None

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

        # RGB tint genome — independent of the evolution property budget so
        # families remain visually traceable regardless of evolution toggle.
        if parent is not None:
            self._inherit_tint(parent)
        else:
            self._init_random_tint()
        self._tint_enabled = tint_enabled

        # Communication genome (also independent of property budget).
        if parent is not None:
            self._inherit_comm(parent)
        else:
            self._init_random_comm()

        # Communication state. _last_broadcast_frame far in the past so the
        # cooldown allows a broadcast immediately when the entity first sees
        # prey. _known_prey_frame far in the past = no fresh knowledge.
        self._last_broadcast_frame = -1_000_000
        self._known_prey_x = 0.0
        self._known_prey_y = 0.0
        self._known_prey_frame = -1_000_000

        # Initialize size state. When growth is on, start small and grow up;
        # otherwise size is fixed at the evolved value. self.size becomes a
        # plain attribute (was a @property) so growth can mutate it cheaply.
        self.reset_size_state(growth_enabled, current_frame)

        self.vx = random.uniform(-self.speed, self.speed)
        self.vy = random.uniform(-self.speed, self.speed)
    
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
    
    # `size` was previously a @property derived from _size_norm. It's now a
    # plain attribute set by reset_size_state / try_grow, since growth needs
    # to mutate it directly. _evolved_size is the value it would take with
    # no growth (i.e. the evolution target).
    def _evolved_size(self):
        return MIN_SIZE + self._size_norm * (MAX_SIZE - MIN_SIZE)

    def reset_size_state(self, growth_enabled, current_frame):
        """Reset size + growth bookkeeping. Called on init and on conversion."""
        if growth_enabled:
            self.size = float(GROWTH_START_SIZE)
            self._fully_grown = False
            self._next_grow_frame = current_frame + GROWTH_INTERVAL_FRAMES
        else:
            self.size = self._evolved_size()
            # Mark as done so try_grow short-circuits cheaply.
            self._fully_grown = True
            self._next_grow_frame = 0
        self._update_scaled_image()

    def try_grow(self, current_frame):
        """One growth tick. Returns True iff the size actually changed.

        Hot path: most calls are for fully-grown entities and exit on the
        first attribute compare. The next_grow_frame check then filters the
        rest until the timer elapses, so RNG only runs on actual attempts.
        """
        if self._fully_grown:
            return False
        if current_frame < self._next_grow_frame:
            return False
        self._next_grow_frame = current_frame + GROWTH_INTERVAL_FRAMES
        if random.random() >= GROWTH_CHANCE:
            return False
        new_size = self.size + GROWTH_INCREMENT
        if new_size >= MAX_SIZE:
            new_size = MAX_SIZE
            self._fully_grown = True
        self.size = new_size
        return True

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
    
    def _init_random_tint(self):
        """Random initial tint within the configured channel range."""
        self._tint_r = random.randint(TINT_INIT_MIN, TINT_INIT_MAX)
        self._tint_g = random.randint(TINT_INIT_MIN, TINT_INIT_MAX)
        self._tint_b = random.randint(TINT_INIT_MIN, TINT_INIT_MAX)

    def _inherit_tint(self, parent):
        """Inherit parent's tint with a small per-channel mutation."""
        m = TINT_MUTATION
        r = parent._tint_r + random.randint(-m, m)
        g = parent._tint_g + random.randint(-m, m)
        b = parent._tint_b + random.randint(-m, m)
        # Clamp into the same range we use for fresh entities so dark drift
        # doesn't accumulate over generations.
        self._tint_r = TINT_INIT_MIN if r < TINT_INIT_MIN else (255 if r > 255 else r)
        self._tint_g = TINT_INIT_MIN if g < TINT_INIT_MIN else (255 if g > 255 else g)
        self._tint_b = TINT_INIT_MIN if b < TINT_INIT_MIN else (255 if b > 255 else b)

    def inherit_tint_from(self, parent):
        """Public hook called by Game on conversion."""
        self._inherit_tint(parent)
        # Caller is expected to call _update_scaled_image() afterward (or
        # reset_size_state, which calls it).

    def _init_random_comm(self):
        """Random initial communication traits within configured ranges."""
        self._comm_radius = random.uniform(MIN_COMM_RADIUS, MAX_COMM_RADIUS)
        self._comm_chance = random.uniform(COMM_CHANCE_MIN, COMM_CHANCE_MAX)

    def _inherit_comm(self, parent):
        """Inherit comm genome from parent with bounded mutation."""
        rad_drift = (MAX_COMM_RADIUS - MIN_COMM_RADIUS) * COMM_MUTATION
        chc_drift = (COMM_CHANCE_MAX - COMM_CHANCE_MIN) * COMM_MUTATION
        r = parent._comm_radius + random.uniform(-rad_drift, rad_drift)
        c = parent._comm_chance + random.uniform(-chc_drift, chc_drift)
        if r < MIN_COMM_RADIUS: r = MIN_COMM_RADIUS
        elif r > MAX_COMM_RADIUS: r = MAX_COMM_RADIUS
        if c < COMM_CHANCE_MIN: c = COMM_CHANCE_MIN
        elif c > COMM_CHANCE_MAX: c = COMM_CHANCE_MAX
        self._comm_radius = r
        self._comm_chance = c

    def inherit_comm_from(self, parent):
        """Public hook called by Game on conversion."""
        self._inherit_comm(parent)

    def set_tint_enabled(self, enabled):
        """Toggle tint rendering for this entity. Cheap if value is unchanged."""
        if self._tint_enabled != enabled:
            self._tint_enabled = enabled
            self._update_scaled_image()

    def _update_scaled_image(self):
        """Build this entity's display surface, tinting if enabled.

        The base scaled image (untinted) is shared via class-level cache.
        Tinted copies are per-entity to avoid an unbounded shared cache when
        every lineage has a slightly different RGB.
        """
        if not self.base_image:
            self.scaled_image = None
            return

        size = int(self.size)
        base_key = (id(self.base_image), size)
        cache = Entity._scaled_image_cache
        base_scaled = cache.get(base_key)
        if base_scaled is None:
            base_scaled = pygame.transform.scale(self.base_image, (size, size))
            cache[base_key] = base_scaled

        if not self._tint_enabled:
            self.scaled_image = base_scaled
            return

        # Per-entity tinted copy. Cost: one Surface.copy + one fill, only
        # when size or tint changes (growth ticks, conversions, or toggle).
        tinted = base_scaled.copy()
        tinted.fill(
            (self._tint_r, self._tint_g, self._tint_b, 255),
            special_flags=pygame.BLEND_RGBA_MULT,
        )
        self.scaled_image = tinted

    def update(self, neighbors, screen_width, screen_height, edge_wrap=False,
               tick=0, share_radius_sq=0.0,
               comm_enabled=False, current_frame=0,
               comm_trigger_chance=0.0, comm_cooldown_frames=0,
               comm_knowledge_frames=0):
        """Update entity position and behavior.

        `neighbors` is the candidate list from the spatial grid (already
        narrowed to entities near this one). It may include `self`.

        If `share_radius_sq > 0`, this entity will try to reuse a cached
        neighbor scan from a same-type entity within sqrt(share_radius_sq)
        that already ran at the current `tick`. The cache stores the leader's
        threat/prey displacement vectors and squared distances; followers
        move as if they were at the leader's position relative to those
        targets. Repulsion is always computed locally.
        """
        sx = self.x
        sy = self.y
        my_type = self.entity_type
        speed = self.speed
        flee_dist = self.flee_distance
        attack_dist = self.attack_distance
        flee_dist_sq = flee_dist * flee_dist
        attack_dist_sq = attack_dist * attack_dist
        prey_type = BEATS[my_type]
        threat_type = BEATEN_BY[my_type]

        # Try to inherit a same-type neighbor's scan result from this tick.
        cache = None
        if share_radius_sq > 0.0:
            for e in neighbors:
                if e is self or e.entity_type != my_type:
                    continue
                if e._cache_tick != tick:
                    continue
                dx = e.x - sx
                dy = e.y - sy
                if dx * dx + dy * dy <= share_radius_sq:
                    cache = e._cache_data
                    break

        repel_dx = 0.0
        repel_dy = 0.0

        if cache is not None:
            # Follower path: reuse leader's threat/prey scan, only compute
            # local same-type repulsion (short-range, cheap).
            (nearest_threat_dx, nearest_threat_dy, nearest_threat_dist_sq,
             nearest_prey_dx, nearest_prey_dy, nearest_prey_dist_sq) = cache
            for entity in neighbors:
                if entity is self or entity.entity_type != my_type:
                    continue
                dx = entity.x - sx
                dy = entity.y - sy
                dist_sq = dx * dx + dy * dy
                if 0 < dist_sq < _REPEL_RADIUS_SQ:
                    dist = math.sqrt(dist_sq)
                    force = ((SAME_TYPE_REPEL_RADIUS - dist) / SAME_TYPE_REPEL_RADIUS
                             * SAME_TYPE_REPEL_STRENGTH)
                    inv_dist = 1.0 / dist
                    repel_dx -= dx * inv_dist * force
                    repel_dy -= dy * inv_dist * force
        else:
            # Leader path: full scan in one pass, publish cache for followers.
            nearest_threat_dx = 0.0
            nearest_threat_dy = 0.0
            nearest_threat_dist_sq = float('inf')
            nearest_prey_dx = 0.0
            nearest_prey_dy = 0.0
            nearest_prey_dist_sq = float('inf')

            for entity in neighbors:
                if entity is self:
                    continue
                dx = entity.x - sx
                dy = entity.y - sy
                dist_sq = dx * dx + dy * dy
                etype = entity.entity_type

                if etype == threat_type:
                    if dist_sq < nearest_threat_dist_sq:
                        nearest_threat_dist_sq = dist_sq
                        nearest_threat_dx = dx
                        nearest_threat_dy = dy
                elif etype == prey_type:
                    if dist_sq < nearest_prey_dist_sq:
                        nearest_prey_dist_sq = dist_sq
                        nearest_prey_dx = dx
                        nearest_prey_dy = dy
                elif dist_sq < _REPEL_RADIUS_SQ and dist_sq > 0:
                    dist = math.sqrt(dist_sq)
                    force = ((SAME_TYPE_REPEL_RADIUS - dist) / SAME_TYPE_REPEL_RADIUS
                             * SAME_TYPE_REPEL_STRENGTH)
                    inv_dist = 1.0 / dist
                    repel_dx -= dx * inv_dist * force
                    repel_dy -= dy * inv_dist * force

        # Publish (or re-publish) cache so subsequent same-type neighbors can
        # chain off this entity. Same tuple is reused across followers.
        if share_radius_sq > 0.0:
            if cache is None:
                cache = (nearest_threat_dx, nearest_threat_dy, nearest_threat_dist_sq,
                         nearest_prey_dx, nearest_prey_dy, nearest_prey_dist_sq)
            self._cache_tick = tick
            self._cache_data = cache

        # Communication: if prey is visible, update self memory and (gated by
        # cooldown + trigger + sender chance) broadcast to nearby same-type
        # entities. Each receiver rolls its own comm_chance to understand.
        if comm_enabled and nearest_prey_dist_sq != float('inf'):
            prey_abs_x = sx + nearest_prey_dx
            prey_abs_y = sy + nearest_prey_dy
            self._known_prey_x = prey_abs_x
            self._known_prey_y = prey_abs_y
            self._known_prey_frame = current_frame

            if (current_frame - self._last_broadcast_frame >= comm_cooldown_frames
                    and random.random() < comm_trigger_chance):
                # Cooldown gates the trigger; sender chance gates the actual send.
                self._last_broadcast_frame = current_frame
                if random.random() < self._comm_chance:
                    radius_sq = self._comm_radius * self._comm_radius
                    for entity in neighbors:
                        if entity is self or entity.entity_type != my_type:
                            continue
                        dx = entity.x - sx
                        dy = entity.y - sy
                        if dx * dx + dy * dy > radius_sq:
                            continue
                        if random.random() < entity._comm_chance:
                            entity._known_prey_x = prey_abs_x
                            entity._known_prey_y = prey_abs_y
                            entity._known_prey_frame = current_frame

        # Behavior: flee if threat in range, else chase visible prey, else
        # chase remembered prey location (fresh knowledge), else wander.
        if nearest_threat_dist_sq < flee_dist_sq:
            dist = math.sqrt(nearest_threat_dist_sq)
            if dist < 0.1:
                dist = 0.1
            inv = (speed * 1.5) / dist
            target_dx = -nearest_threat_dx * inv
            target_dy = -nearest_threat_dy * inv
        elif nearest_prey_dist_sq < attack_dist_sq:
            dist = math.sqrt(nearest_prey_dist_sq)
            if dist < 0.1:
                dist = 0.1
            inv = speed / dist
            target_dx = nearest_prey_dx * inv
            target_dy = nearest_prey_dy * inv
        elif (comm_enabled
              and current_frame - self._known_prey_frame < comm_knowledge_frames):
            # Move toward remembered prey location (own observation or relayed).
            dx = self._known_prey_x - sx
            dy = self._known_prey_y - sy
            dist_sq = dx * dx + dy * dy
            if dist_sq > 1.0:
                dist = math.sqrt(dist_sq)
                inv = speed / dist
                target_dx = dx * inv
                target_dy = dy * inv
            else:
                # Reached the location — drop the stale memory and wander.
                self._known_prey_frame = -1_000_000
                target_dx = self.vx
                target_dy = self.vy
        else:
            if random.random() < 0.02:
                self.vx = random.uniform(-speed, speed)
                self.vy = random.uniform(-speed, speed)
            target_dx = self.vx
            target_dy = self.vy

        self.vx = self.vx * 0.9 + target_dx * 0.1 + repel_dx
        self.vy = self.vy * 0.9 + target_dy * 0.1 + repel_dy

        self.x = sx + self.vx
        self.y = sy + self.vy
        
        # Handle edges (wrap or bounce)
        margin = int(self.size) // 2
        if edge_wrap:
            # Wrap around edges
            if self.x < -margin:
                self.x = screen_width + margin
            elif self.x > screen_width + margin:
                self.x = -margin
            if self.y < -margin:
                self.y = screen_height + margin
            elif self.y > screen_height + margin:
                self.y = -margin
        else:
            # Bounce off walls (using individual size)
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
        """Calculate distance to another entity."""
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)
    
    def collides_with(self, other):
        """Check if this entity collides with another."""
        # Use average of both entity sizes for collision
        collision_dist = (self.size + other.size) / 2
        return self.distance_to(other) < collision_dist
    
    def draw(self, screen):
        """Draw the entity on the screen."""
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
        """Copy evolutionary properties from a parent (winner in collision).

        Caller is responsible for calling reset_size_state() afterward, since
        growth state (and therefore the displayed size) depends on whether
        growth is enabled at the game level.
        """
        self._inherit_balanced(parent)
