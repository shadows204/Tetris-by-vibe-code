"""
Tetris — Full-featured implementation
Features: resizable window, scoring, levels, menu, pause, high-score
"""

import pygame
import random
import sys
import json
import os

# ---------------------------------------------------------------------------
# Constants & colour palette
# ---------------------------------------------------------------------------

TITLE = "Tetris"
FPS = 60

# Logical grid dimensions
COLS = 10
ROWS = 20

# Colour definitions (R, G, B)
BLACK       = (  0,   0,   0)
WHITE       = (255, 255, 255)
DARK_GREY   = ( 30,  30,  30)
MID_GREY    = ( 60,  60,  60)
LIGHT_GREY  = (180, 180, 180)
ACCENT      = ( 80, 160, 255)
ACCENT_DARK = ( 40,  80, 140)

# One colour per tetromino type (I O T S Z J L)
PIECE_COLOURS = [
    (  0, 240, 240),   # I – cyan
    (240, 240,   0),   # O – yellow
    (160,   0, 240),   # T – purple
    (  0, 240,   0),   # S – green
    (240,   0,   0),   # Z – red
    (  0,   0, 240),   # J – blue
    (240, 160,   0),   # L – orange
]

# Tetromino shapes  (each rotation is a list of (col, row) offsets from pivot)
SHAPES = {
    "I": [
        [(0,1),(1,1),(2,1),(3,1)],
        [(2,0),(2,1),(2,2),(2,3)],
        [(0,2),(1,2),(2,2),(3,2)],
        [(1,0),(1,1),(1,2),(1,3)],
    ],
    "O": [
        [(1,0),(2,0),(1,1),(2,1)],
    ],
    "T": [
        [(1,0),(0,1),(1,1),(2,1)],
        [(1,0),(1,1),(2,1),(1,2)],
        [(0,1),(1,1),(2,1),(1,2)],
        [(1,0),(0,1),(1,1),(1,2)],
    ],
    "S": [
        [(1,0),(2,0),(0,1),(1,1)],
        [(1,0),(1,1),(2,1),(2,2)],
        [(1,1),(2,1),(0,2),(1,2)],
        [(0,0),(0,1),(1,1),(1,2)],
    ],
    "Z": [
        [(0,0),(1,0),(1,1),(2,1)],
        [(2,0),(1,1),(2,1),(1,2)],
        [(0,1),(1,1),(1,2),(2,2)],
        [(1,0),(0,1),(1,1),(0,2)],
    ],
    "J": [
        [(0,0),(0,1),(1,1),(2,1)],
        [(1,0),(2,0),(1,1),(1,2)],
        [(0,1),(1,1),(2,1),(2,2)],
        [(1,0),(1,1),(0,2),(1,2)],
    ],
    "L": [
        [(2,0),(0,1),(1,1),(2,1)],
        [(1,0),(1,1),(1,2),(2,2)],
        [(0,1),(1,1),(2,1),(0,2)],
        [(0,0),(1,0),(1,1),(1,2)],
    ],
}

SHAPE_NAMES = list(SHAPES.keys())   # fixed order → index → colour

# Scoring table (lines cleared at once → base points)
LINE_SCORES = {1: 100, 2: 300, 3: 500, 4: 800}

# ---------------------------------------------------------------------------
# Highscore persistence
# ---------------------------------------------------------------------------

SCORE_FILE = os.path.join(os.path.dirname(__file__), "highscores.json")

def load_highscores() -> list[dict]:
    try:
        with open(SCORE_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data[:10]
    except Exception:
        pass
    return []

def save_highscores(scores: list[dict]) -> None:
    try:
        with open(SCORE_FILE, "w") as f:
            json.dump(scores[:10], f, indent=2)
    except Exception:
        pass

def insert_score(scores: list[dict], name: str, value: int, level: int) -> list[dict]:
    scores.append({"name": name, "score": value, "level": level})
    scores.sort(key=lambda e: e["score"], reverse=True)
    return scores[:10]

# ---------------------------------------------------------------------------
# Piece
# ---------------------------------------------------------------------------

class Piece:
    def __init__(self, kind: str | None = None):
        self.kind  = kind or random.choice(SHAPE_NAMES)
        self.index = SHAPE_NAMES.index(self.kind)
        self.colour = PIECE_COLOURS[self.index]
        self.rot   = 0
        self.x     = COLS // 2 - 2
        self.y     = 0

    @property
    def cells(self) -> list[tuple[int, int]]:
        rots = SHAPES[self.kind]
        return [(self.x + c, self.y + r) for c, r in rots[self.rot % len(rots)]]

    def rotated_cells(self, delta: int = 1) -> list[tuple[int, int]]:
        rots = SHAPES[self.kind]
        rot  = (self.rot + delta) % len(rots)
        return [(self.x + c, self.y + r) for c, r in rots[rot]]

# ---------------------------------------------------------------------------
# Board (game logic)
# ---------------------------------------------------------------------------

class Board:
    def __init__(self):
        self.grid: list[list[int | None]] = [[None] * COLS for _ in range(ROWS)]
        self.score    = 0
        self.lines    = 0
        self.level    = 1
        self.combo    = 0
        self.game_over = False
        self._bag: list[str] = []
        self.current  = self._next_piece()
        self.next     = self._next_piece()
        self.hold: Piece | None = None
        self.hold_used = False
        self._drop_acc = 0.0   # accumulated fall time (seconds)
        self._lock_delay = 0.0
        self._lock_limit = 0.5  # lock immediately on landing

    # -- bag randomiser (7-bag) ------------------------------------------
    def _next_piece(self) -> Piece:
        if not self._bag:
            self._bag = SHAPE_NAMES[:]
            random.shuffle(self._bag)
        return Piece(self._bag.pop())

    # -- collision detection ---------------------------------------------
    def _valid(self, cells: list[tuple[int, int]]) -> bool:
        for x, y in cells:
            if x < 0 or x >= COLS or y >= ROWS:
                return False
            if y >= 0 and self.grid[y][x] is not None:
                return False
        return True

    # -- ghost piece (drop-shadow) ----------------------------------------
    def ghost_cells(self) -> list[tuple[int, int]]:
        dy = 0
        p = self.current
        while self._valid([(x, y + dy + 1) for x, y in p.cells]):
            dy += 1
        return [(x, y + dy) for x, y in p.cells]

    # -- movement ---------------------------------------------------------
    def move(self, dx: int) -> bool:
        cells = [(x + dx, y) for x, y in self.current.cells]
        if self._valid(cells):
            self.current.x += dx
            return True
        return False

    def rotate(self, delta: int = 1) -> bool:
        new_cells = self.current.rotated_cells(delta)
        # basic wall kick: try offsets 0, ±1, ±2
        for kick in [0, -1, 1, -2, 2]:
            kicked = [(x + kick, y) for x, y in new_cells]
            if self._valid(kicked):
                self.current.x += kick
                self.current.rot = (self.current.rot + delta) % len(SHAPES[self.current.kind])
                return True
        return False

    def soft_drop(self) -> bool:
        cells = [(x, y + 1) for x, y in self.current.cells]
        if self._valid(cells):
            self.current.y += 1
            self.score += 1
            self._drop_acc = 0.0
            return True
        return False

    def hard_drop(self) -> None:
        while self.soft_drop():
            pass
        self._lock()

    def hold_piece(self) -> None:
        if self.hold_used:
            return
        if self.hold is None:
            self.hold = Piece(self.current.kind)
            self.current = self.next
            self.next = self._next_piece()
        else:
            old_kind = self.hold.kind
            self.hold = Piece(self.current.kind)
            self.current = Piece(old_kind)
        self.hold_used = True
        self._drop_acc = 0.0

    # -- locking & line clearing ------------------------------------------
    def _lock(self) -> None:
        for x, y in self.current.cells:
            if y < 0:
                self.game_over = True
                return
            self.grid[y][x] = self.current.index

        cleared = self._clear_lines()
        if cleared:
            self.combo += 1
            base = LINE_SCORES.get(cleared, 0)
            self.score += base * self.level + (50 * self.combo * self.level if self.combo > 1 else 0)
            self.lines += cleared
            self.level = self.lines // 10 + 1
        else:
            self.combo = 0

        self.current = self.next
        self.next = self._next_piece()
        self.hold_used = False
        self._drop_acc = 0.0
        self._lock_delay = 0.0

        if not self._valid(self.current.cells):
            self.game_over = True

    def _clear_lines(self) -> int:
        full = [i for i, row in enumerate(self.grid) if all(c is not None for c in row)]
        for i in full:
            del self.grid[i]
            self.grid.insert(0, [None] * COLS)
        return len(full)

    # -- gravity update ----------------------------------------------------
    def update(self, dt: float) -> None:
        if self.game_over:
            return
        fall_speed = max(0.05, 1.0 - (self.level - 1) * 0.08)   # seconds per row

        cells_below = [(x, y + 1) for x, y in self.current.cells]
        grounded = not self._valid(cells_below)

        if grounded:
            # Accumulate lock delay every frame (not gated by fall tick)
            self._lock_delay += dt
            if self._lock_delay >= self._lock_limit:
                self._lock()
        else:
            self._lock_delay = 0.0
            self._drop_acc += dt
            if self._drop_acc >= fall_speed:
                self._drop_acc -= fall_speed
                # Re-check; piece might have been moved since top of frame
                cells_below2 = [(x, y + 1) for x, y in self.current.cells]
                if self._valid(cells_below2):
                    self.current.y += 1

# ---------------------------------------------------------------------------
# Renderer  (all drawing scaled to current window size)
# ---------------------------------------------------------------------------

class Renderer:
    def __init__(self, surface: pygame.Surface):
        self.surf = surface

    def _metrics(self) -> tuple[int, int, int, int, int]:
        """Return (cell_size, board_x, board_y, side_w, top_h)."""
        W, H = self.surf.get_size()
        cell  = min((H - 40) // ROWS, (W - 220) // COLS)
        cell  = max(cell, 16)
        bw    = cell * COLS
        bh    = cell * ROWS
        bx    = (W - bw - 160) // 2          # leave room for panel on right
        by    = (H - bh) // 2
        return cell, bx, by, bw, bh

    def draw_board(self, board: Board) -> None:
        cell, bx, by, bw, bh = self._metrics()
        surf = self.surf

        # background behind board
        pygame.draw.rect(surf, DARK_GREY, (bx, by, bw, bh))
        # grid lines
        for c in range(COLS + 1):
            pygame.draw.line(surf, MID_GREY, (bx + c * cell, by), (bx + c * cell, by + bh))
        for r in range(ROWS + 1):
            pygame.draw.line(surf, MID_GREY, (bx, by + r * cell), (bx + bw, by + r * cell))

        # locked cells
        for r, row in enumerate(board.grid):
            for c, idx in enumerate(row):
                if idx is not None:
                    self._draw_cell(bx + c * cell, by + r * cell, cell, PIECE_COLOURS[idx])

        # ghost
        for gx, gy in board.ghost_cells():
            if gy >= 0:
                colour = board.current.colour
                ghost_col = tuple(max(0, v - 140) for v in colour)
                pygame.draw.rect(surf, ghost_col,
                                 (bx + gx * cell + 2, by + gy * cell + 2, cell - 4, cell - 4), 2)

        # current piece
        for px, py in board.current.cells:
            if py >= 0:
                self._draw_cell(bx + px * cell, by + py * cell, cell, board.current.colour)

        # board border
        pygame.draw.rect(surf, ACCENT, (bx, by, bw, bh), 2)

    def _draw_cell(self, x: int, y: int, size: int, colour: tuple) -> None:
        rect = pygame.Rect(x + 1, y + 1, size - 2, size - 2)
        pygame.draw.rect(self.surf, colour, rect)
        # highlight / shadow for 3-D feel
        light = tuple(min(255, v + 60) for v in colour)
        dark  = tuple(max(0,   v - 60) for v in colour)
        pygame.draw.line(self.surf, light, (x + 1, y + 1), (x + size - 2, y + 1))
        pygame.draw.line(self.surf, light, (x + 1, y + 1), (x + 1, y + size - 2))
        pygame.draw.line(self.surf, dark,  (x + size - 2, y + 1), (x + size - 2, y + size - 2))
        pygame.draw.line(self.surf, dark,  (x + 1, y + size - 2), (x + size - 2, y + size - 2))

    def draw_panel(self, board: Board, fonts: dict) -> None:
        cell, bx, by, bw, bh = self._metrics()
        px = bx + bw + 16
        py = by

        def label(text, y_off, font_key="sm", colour=LIGHT_GREY):
            img = fonts[font_key].render(text, True, colour)
            self.surf.blit(img, (px, py + y_off))

        def value(text, y_off, colour=WHITE):
            img = fonts["md"].render(text, True, colour)
            self.surf.blit(img, (px, py + y_off))

        label("SCORE",  0, colour=ACCENT)
        value(str(board.score), 22)
        label("LEVEL",  70, colour=ACCENT)
        value(str(board.level), 92)
        label("LINES", 140, colour=ACCENT)
        value(str(board.lines), 162)
        label("COMBO", 210, colour=ACCENT)
        value(f"x{board.combo}", 232)

        # Next piece preview
        label("NEXT",  300, colour=ACCENT)
        self._draw_mini(board.next, px, py + 325, cell)

        # Hold piece
        label("HOLD",  430, colour=ACCENT if not board.hold_used else MID_GREY)
        if board.hold:
            self._draw_mini(board.hold, px, py + 455, cell,
                            dimmed=board.hold_used)

        # Controls hint (bottom of panel)
        hints = [
            ("← →", "Move"),
            ("↑ / Z", "Rotate"),
            ("↓",    "Soft drop"),
            ("Space", "Hard drop"),
            ("C",    "Hold"),
            ("P",    "Pause"),
            ("Esc",  "Menu"),
        ]
        hint_y = py + bh - len(hints) * 20
        for key, desc in hints:
            img = fonts["xs"].render(f"{key}: {desc}", True, MID_GREY)
            self.surf.blit(img, (px, hint_y))
            hint_y += 20

    def _draw_mini(self, piece: Piece, px: int, py: int, cell: int,
                   dimmed: bool = False) -> None:
        mini = max(cell // 2, 10)
        cells = SHAPES[piece.kind][0]
        colour = tuple(v // 2 for v in piece.colour) if dimmed else piece.colour
        for (c, r) in cells:
            self._draw_cell(px + c * mini, py + r * mini, mini, colour)

    def draw_overlay(self, text: str, sub: str, fonts: dict) -> None:
        W, H = self.surf.get_size()
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.surf.blit(overlay, (0, 0))
        img = fonts["lg"].render(text, True, WHITE)
        self.surf.blit(img, img.get_rect(center=(W // 2, H // 2 - 30)))
        img2 = fonts["sm"].render(sub, True, LIGHT_GREY)
        self.surf.blit(img2, img2.get_rect(center=(W // 2, H // 2 + 20)))

# ---------------------------------------------------------------------------
# Shared font loader
# ---------------------------------------------------------------------------

def make_fonts() -> dict:
    pygame.font.init()
    try:
        base = pygame.font.match_font("consolas,dejavusansmono,ubuntumono,monospace")
    except Exception:
        base = None
    def f(size): return pygame.font.Font(base, size)
    return {"xs": f(13), "sm": f(17), "md": f(22), "lg": f(40), "xl": f(64)}

# ---------------------------------------------------------------------------
# Input handler (DAS / ARR)
# ---------------------------------------------------------------------------

class InputHandler:
    DAS = 0.17   # delay auto-shift (seconds)
    ARR = 0.05   # auto-repeat rate (seconds)

    def __init__(self):
        self._held: dict[int, float] = {}   # key → time held
        self._repeated: dict[int, float] = {}

    def update(self, dt: float, pressed: set[int]) -> list[int]:
        """Return list of keys that should trigger an action this frame."""
        actions = []
        for key in pressed:
            if key not in self._held:
                self._held[key] = 0.0
                self._repeated[key] = 0.0
                actions.append(key)
            else:
                self._held[key] += dt
                if self._held[key] >= self.DAS:
                    self._repeated[key] += dt
                    while self._repeated[key] >= self.ARR:
                        self._repeated[key] -= self.ARR
                        actions.append(key)
        # clear released keys
        for key in list(self._held.keys()):
            if key not in pressed:
                del self._held[key]
                del self._repeated[key]
        return actions


# ---------------------------------------------------------------------------
# Name-input screen
# ---------------------------------------------------------------------------

def name_input_screen(screen: pygame.Surface, fonts: dict, score: int, level: int) -> str:
    clock = pygame.time.Clock()
    name  = ""
    cursor_vis = True
    cursor_timer = 0.0

    while True:
        dt = clock.tick(FPS) / 1000.0
        cursor_timer += dt
        if cursor_timer >= 0.5:
            cursor_timer = 0.0
            cursor_vis = not cursor_vis

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN and name.strip():
                    return name.strip()[:12]
                elif event.key == pygame.K_BACKSPACE:
                    name = name[:-1]
                elif event.key == pygame.K_ESCAPE:
                    return "Player"
                elif len(name) < 12 and event.unicode.isprintable():
                    name += event.unicode

        W, H = screen.get_size()
        screen.fill(BLACK)

        title = fonts["lg"].render("GAME OVER", True, (220, 60, 60))
        screen.blit(title, title.get_rect(center=(W // 2, H // 2 - 120)))

        s_img = fonts["md"].render(f"Score: {score}   Level: {level}", True, LIGHT_GREY)
        screen.blit(s_img, s_img.get_rect(center=(W // 2, H // 2 - 60)))

        prompt = fonts["sm"].render("Enter your name:", True, ACCENT)
        screen.blit(prompt, prompt.get_rect(center=(W // 2, H // 2)))

        display = name + ("|" if cursor_vis else " ")
        n_img = fonts["md"].render(display, True, WHITE)
        screen.blit(n_img, n_img.get_rect(center=(W // 2, H // 2 + 40)))

        hint = fonts["xs"].render("[Enter] confirm   [Esc] skip", True, MID_GREY)
        screen.blit(hint, hint.get_rect(center=(W // 2, H // 2 + 90)))

        pygame.display.flip()

# ---------------------------------------------------------------------------
# High-score screen
# ---------------------------------------------------------------------------

def highscore_screen(screen: pygame.Surface, fonts: dict,
                     scores: list[dict], highlight_name: str = "") -> None:
    clock = pygame.time.Clock()
    while True:
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                return
            if event.type == pygame.MOUSEBUTTONDOWN:
                return

        W, H = screen.get_size()
        screen.fill(BLACK)

        title = fonts["lg"].render("HIGH SCORES", True, ACCENT)
        screen.blit(title, title.get_rect(center=(W // 2, 60)))

        headers = fonts["sm"].render(f"{'#':<4}{'Name':<16}{'Score':>10}  {'Level':>6}", True, ACCENT_DARK)
        screen.blit(headers, headers.get_rect(center=(W // 2, 120)))

        for i, entry in enumerate(scores):
            col = ACCENT if entry["name"] == highlight_name else WHITE
            line = fonts["sm"].render(
                f"{i+1:<4}{entry['name']:<16}{entry['score']:>10}  {entry['level']:>6}", True, col)
            screen.blit(line, line.get_rect(center=(W // 2, 160 + i * 32)))

        hint = fonts["xs"].render("Press any key to return", True, MID_GREY)
        screen.blit(hint, hint.get_rect(center=(W // 2, H - 40)))
        pygame.display.flip()

# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

class Button:
    def __init__(self, text: str, rect: pygame.Rect):
        self.text = text
        self.rect = rect
        self.hovered = False

    def draw(self, surf: pygame.Surface, fonts: dict) -> None:
        col = ACCENT if self.hovered else ACCENT_DARK
        border = ACCENT if self.hovered else MID_GREY
        pygame.draw.rect(surf, col, self.rect, border_radius=8)
        pygame.draw.rect(surf, border, self.rect, 2, border_radius=8)
        img = fonts["md"].render(self.text, True, WHITE)
        surf.blit(img, img.get_rect(center=self.rect.center))

    def check(self, pos: tuple[int, int]) -> bool:
        self.hovered = self.rect.collidepoint(pos)
        return self.hovered

    def clicked(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)


def menu_screen(screen: pygame.Surface, fonts: dict) -> str:
    """Return one of: 'play', 'scores', 'quit'"""
    clock = pygame.time.Clock()
    actions = ["Play", "High Scores", "Quit"]
    buttons: list[Button] = []

    while True:
        clock.tick(FPS)
        W, H = screen.get_size()

        # Rebuild buttons each frame so they adapt to window resize
        bw, bh = 240, 52
        bx = W // 2 - bw // 2
        by_start = H // 2 - (len(actions) * (bh + 16)) // 2
        buttons = [
            Button(a, pygame.Rect(bx, by_start + i * (bh + 16), bw, bh))
            for i, a in enumerate(actions)
        ]

        mouse = pygame.mouse.get_pos()
        for b in buttons:
            b.check(mouse)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                    return "play"
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, b in enumerate(buttons):
                    if b.clicked(mouse):
                        return ["play", "scores", "quit"][i]

        # Draw
        screen.fill(BLACK)
        # Decorative falling blocks background (static for simplicity)
        for col_idx, col in enumerate(PIECE_COLOURS):
            for row_idx in range(0, H, 60):
                block_col = tuple(v // 5 for v in col)
                pygame.draw.rect(screen, block_col,
                                 (col_idx * (W // 7), row_idx, W // 7 - 2, 28))

        # Title
        title_img = fonts["xl"].render("TETRIS", True, ACCENT)
        shadow_img = fonts["xl"].render("TETRIS", True, ACCENT_DARK)
        cx = W // 2
        screen.blit(shadow_img, shadow_img.get_rect(center=(cx + 3, H // 4 + 3)))
        screen.blit(title_img,  title_img.get_rect(center=(cx, H // 4)))

        sub = fonts["sm"].render("Use ← → ↓ Space C P Esc", True, LIGHT_GREY)
        screen.blit(sub, sub.get_rect(center=(cx, H // 4 + 50)))

        for b in buttons:
            b.draw(screen, fonts)

        pygame.display.flip()

# ---------------------------------------------------------------------------
# Pause menu
# ---------------------------------------------------------------------------

def pause_menu_screen(screen: pygame.Surface, fonts: dict) -> str:
    """Return one of: 'resume', 'restart', 'menu'"""
    clock = pygame.time.Clock()
    actions = ["Continue (Esc)", "Restart", "Main Menu"]
    buttons: list[Button] = []
    selected = 0   # default to "Continue"

    while True:
        clock.tick(FPS)
        W, H = screen.get_size()

        # Rebuild buttons each frame
        bw, bh = 280, 52
        bx = W // 2 - bw // 2
        by_start = H // 2 - (len(actions) * (bh + 16)) // 2
        buttons = [
            Button(a, pygame.Rect(bx, by_start + i * (bh + 16), bw, bh))
            for i, a in enumerate(actions)
        ]

        mouse = pygame.mouse.get_pos()
        for i, b in enumerate(buttons):
            b.check(mouse)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return "resume"    # Esc continues by default
                if event.key == pygame.K_UP:
                    selected = (selected - 1) % len(actions)
                if event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(actions)
                if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                    return ["resume", "restart", "menu"][selected]
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, b in enumerate(buttons):
                    if b.clicked(mouse):
                        return ["resume", "restart", "menu"][i]

        # Draw
        screen.fill(BLACK)

        # Overlay
        W, H = screen.get_size()
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        screen.blit(overlay, (0, 0))

        # Title
        title_img = fonts["lg"].render("PAUSED", True, ACCENT)
        screen.blit(title_img, title_img.get_rect(center=(W // 2, H // 2 - 120)))

        # Buttons with highlight on selected
        for i, b in enumerate(buttons):
            col = ACCENT if i == selected else ACCENT_DARK
            border = ACCENT if i == selected else MID_GREY
            pygame.draw.rect(screen, col, b.rect, border_radius=8)
            pygame.draw.rect(screen, border, b.rect, 2, border_radius=8)
            img = fonts["md"].render(b.text, True, WHITE)
            screen.blit(img, img.get_rect(center=b.rect.center))

        hint = fonts["xs"].render("↑ ↓ to select   [Enter] confirm   [Esc] resume", True, MID_GREY)
        screen.blit(hint, hint.get_rect(center=(W // 2, H - 40)))

        pygame.display.flip()

# ---------------------------------------------------------------------------
# Main game loop
# ---------------------------------------------------------------------------

def game_loop(screen: pygame.Surface, fonts: dict, scores: list[dict]) -> list[dict]:
    clock   = pygame.time.Clock()
    board   = Board()
    renderer = Renderer(screen)
    inp     = InputHandler()
    paused  = False

    move_keys = {
        pygame.K_LEFT:  -1,
        pygame.K_RIGHT:  1,
    }
    drop_keys = {pygame.K_DOWN}

    while True:
        dt = clock.tick(FPS) / 1000.0

        # ---- events ----
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # Show pause menu
                    pause_result = pause_menu_screen(screen, fonts)
                    if pause_result == "resume":
                        paused = False
                    elif pause_result == "restart":
                        return game_loop(screen, fonts, scores)  # Restart game
                    elif pause_result == "menu":
                        return scores  # back to menu
                if event.key == pygame.K_p:
                    paused = not paused
                if not paused and not board.game_over:
                    if event.key in (pygame.K_UP, pygame.K_x):
                        board.rotate(1)
                    if event.key == pygame.K_z:
                        board.rotate(-1)
                    if event.key == pygame.K_SPACE:
                        board.hard_drop()
                    if event.key == pygame.K_c:
                        board.hold_piece()

        if not paused and not board.game_over:
            # DAS / ARR movement
            keys_down = pygame.key.get_pressed()
            pressed_set: set[int] = set()
            for k in list(move_keys) + list(drop_keys):
                if keys_down[k]:
                    pressed_set.add(k)

            for action in inp.update(dt, pressed_set):
                if action in move_keys:
                    board.move(move_keys[action])
                elif action in drop_keys:
                    board.soft_drop()

            board.update(dt)

        # ---- draw ----
        screen.fill(BLACK)
        renderer.draw_board(board)
        renderer.draw_panel(board, fonts)

        if paused:
            renderer.draw_overlay("PAUSED", "P  to resume   Esc for menu", fonts)

        if board.game_over:
            renderer.draw_overlay("GAME OVER",
                                  f"Score: {board.score}  |  Press any key", fonts)
            pygame.display.flip()
            # Wait for keypress
            waiting = True
            while waiting:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit(); sys.exit()
                    if event.type == pygame.KEYDOWN:
                        waiting = False
            # Name entry + high-score insertion
            name = name_input_screen(screen, fonts, board.score, board.level)
            scores = insert_score(scores, name, board.score, board.level)
            save_highscores(scores)
            highscore_screen(screen, fonts, scores, highlight_name=name)
            return scores

        pygame.display.flip()

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    pygame.init()
    pygame.display.set_caption(TITLE)
    screen = pygame.display.set_mode((800, 700), pygame.RESIZABLE)
    pygame.display.set_icon(
        pygame.transform.scale(
            pygame.Surface((32, 32)),
            (32, 32)
        )
    )
    fonts  = make_fonts()
    scores = load_highscores()

    while True:
        action = menu_screen(screen, fonts)
        if action == "play":
            scores = game_loop(screen, fonts, scores)
        elif action == "scores":
            highscore_screen(screen, fonts, scores)
        elif action == "quit":
            break

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()



