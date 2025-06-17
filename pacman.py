import sys
import random
from collections import deque

from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QPoint
from PyQt5.QtGui import QFont, QPainter, QColor, QBrush, QPen, QPainterPath

WIDTH, HEIGHT = 400, 400
CELL_SIZE = 20
GAME_SPEED_MS = 200

MAZE_ROWS = HEIGHT // CELL_SIZE
MAZE_COLS = WIDTH // CELL_SIZE

NORMAL = 0
FRIGHTENED = 1
EATEN = 2

FRIGHTENED_DURATION_MS = 9000
GHOST_REGEN_TIME_MS = 4000

GHOST_HOUSE_RECT_TOP = MAZE_ROWS // 2 - 2
GHOST_HOUSE_RECT_LEFT = MAZE_COLS // 2 - 2
GHOST_HOUSE_RECT_BOTTOM = GHOST_HOUSE_RECT_TOP + 4
GHOST_HOUSE_RECT_RIGHT = GHOST_HOUSE_RECT_LEFT + 4
GHOST_HOUSE_EXIT_POINT = (GHOST_HOUSE_RECT_TOP - 1, GHOST_HOUSE_RECT_LEFT + 1)

GHOST_HOUSE_CELLS = []
for r in range(GHOST_HOUSE_RECT_TOP, GHOST_HOUSE_RECT_BOTTOM):
    for c in range(GHOST_HOUSE_RECT_LEFT, GHOST_HOUSE_RECT_RIGHT):
        GHOST_HOUSE_CELLS.append((r, c))

class GameCanvas(QWidget):
    game_over_signal = pyqtSignal()
    score_changed_signal = pyqtSignal(int)
    game_win_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(WIDTH, HEIGHT)
        self.setStyleSheet("background-color: #000000;")
        self.setFocusPolicy(Qt.StrongFocus)

        self.game_timer = QTimer(self)
        self.game_timer.timeout.connect(self.game_loop_update)
        self.frightened_timer = QTimer(self)
        self.frightened_timer.setSingleShot(True)
        self.frightened_timer.timeout.connect(self.end_frightened_mode)

        self.ghost_regen_timers = {}

        self.reset_game()

    def reset_game(self):
        self.maze = self.generate_random_maze()
        self.pacman_pos = self.find_random_path_cell_outside_ghost_house()
        self.pacman_direction = (0, 0)
        self.next_pacman_direction = (0,0)

        self.ghosts = []
        self.initialize_ghosts()

        self.dots = set()
        self.power_pellets = set()
        self.initialize_dots_and_pellets()

        self.score = 0
        self.game_running = False
        self.game_over = False
        self.update()

    def generate_random_maze(self):
        maze = [[1 for _ in range(MAZE_COLS)] for _ in range(MAZE_ROWS)]
        
        start_r, start_c = random.randrange(1, MAZE_ROWS - 1, 2), random.randrange(1, MAZE_COLS - 1, 2)
        maze[start_r][start_c] = 0

        frontier = []
        for dr, dc in [(0, 2), (0, -2), (2, 0), (-2, 0)]:
            nr, nc = start_r + dr, start_c + dc
            if 0 < nr < MAZE_ROWS - 1 and 0 < nc < MAZE_COLS - 1:
                frontier.append(((nr, nc), (start_r, start_c)))

        while frontier:
            idx = random.randrange(len(frontier))
            (r, c), (pr, pc) = frontier.pop(idx)

            if maze[r][c] == 1:
                maze[r][c] = 0
                maze[(r + pr) // 2][(c + pc) // 2] = 0

                for dr, dc in [(0, 2), (0, -2), (2, 0), (-2, 0)]:
                    nr, nc = r + dr, c + dc
                    if 0 < nr < MAZE_ROWS - 1 and 0 < nc < MAZE_COLS - 1 and maze[nr][nc] == 1:
                        frontier.append(((nr, nc), (r, c)))
        
        for r in range(GHOST_HOUSE_RECT_TOP, GHOST_HOUSE_RECT_BOTTOM):
            for c in range(GHOST_HOUSE_RECT_LEFT, GHOST_HOUSE_RECT_RIGHT):
                if 0 <= r < MAZE_ROWS and 0 <= c < MAZE_COLS:
                    maze[r][c] = 0
        
        if 0 <= GHOST_HOUSE_EXIT_POINT[0] < MAZE_ROWS and 0 <= GHOST_HOUSE_EXIT_POINT[1] < MAZE_COLS:
            maze[GHOST_HOUSE_EXIT_POINT[0]][GHOST_HOUSE_EXIT_POINT[1]] = 0

        return maze

    def find_random_path_cell_outside_ghost_house(self):
        valid_cells = []
        for r in range(1, MAZE_ROWS - 1):
            for c in range(1, MAZE_COLS - 1):
                if self.maze[r][c] == 0 and not self.is_in_ghost_home((r, c)):
                    valid_cells.append((r, c))
        if valid_cells:
            return random.choice(valid_cells)
        return (1, 1)

    def is_in_ghost_home(self, pos):
        r, c = pos
        return GHOST_HOUSE_RECT_TOP <= r < GHOST_HOUSE_RECT_BOTTOM and \
               GHOST_HOUSE_RECT_LEFT <= c < GHOST_HOUSE_RECT_RIGHT

    def initialize_dots_and_pellets(self):
        path_cells = []
        for r in range(MAZE_ROWS):
            for c in range(MAZE_COLS):
                if self.maze[r][c] == 0 and \
                   not self.is_in_ghost_home((r, c)) and \
                   (r, c) != self.pacman_pos:
                    path_cells.append((r, c))

        num_power_pellets = min(4, len(path_cells) // 10)
        
        power_pellet_candidates = [p for p in path_cells if not self.is_in_ghost_home(p)]

        for _ in range(num_power_pellets):
            if power_pellet_candidates:
                pellet_pos = random.choice(power_pellet_candidates)
                self.power_pellets.add(pellet_pos)
                power_pellet_candidates.remove(pellet_pos)
            else:
                break

        for r, c in path_cells:
            if (r, c) not in self.power_pellets:
                self.dots.add((r, c))

    def initialize_ghosts(self):
        ghost_colors = [QColor("#FF0000"), QColor("#FFA500"), QColor("#00FFFF"), QColor("#FFC0CB")]
        
        ghost_home_spawn_points = [p for p in GHOST_HOUSE_CELLS if self.maze[p[0]][p[1]] == 0]
        random.shuffle(ghost_home_spawn_points)

        for i in range(4):
            if not ghost_home_spawn_points:
                break
            
            start_pos = ghost_home_spawn_points.pop()

            self.ghosts.append({
                'pos': start_pos,
                'direction': (0, 0),
                'state': NORMAL,
                'start_pos': start_pos,
                'color': ghost_colors[i % len(ghost_colors)],
                'regen_timer': None
            })

    def game_loop_update(self):
        if not self.game_running or self.game_over:
            return

        self.move_pacman()
        self.move_ghosts()
        self.check_collisions()
        self.update()

        if not self.dots and not self.power_pellets:
            self.game_win_signal.emit()

    def is_valid_move(self, pos):
        r, c = pos
        if not (0 <= r < MAZE_ROWS and 0 <= c < MAZE_COLS):
            return False
        return self.maze[r][c] != 1

    def get_possible_directions(self, current_pos, current_dir, is_ghost=False, ghost_state=NORMAL):
        r, c = current_pos
        possible_dirs = []
        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            new_pos = (r + dr, c + dc)
            
            if is_ghost and ghost_state == EATEN:
                if self.is_valid_move(new_pos) or new_pos == GHOST_HOUSE_EXIT_POINT:
                    exit_r, exit_c = GHOST_HOUSE_EXIT_POINT
                    dist_to_exit = abs(new_pos[0] - exit_r) + abs(new_pos[1] - exit_c)
                    
                    if dist_to_exit < abs(current_pos[0] - exit_r) + abs(current_pos[1] - exit_c):
                        possible_dirs.insert(0, (dr, dc))
                    else:
                        possible_dirs.append((dr, dc))
            elif self.is_valid_move(new_pos):
                if (dr, dc) != (-current_dir[0], -current_dir[1]) or len(possible_dirs) == 0:
                     possible_dirs.append((dr, dc))
        return possible_dirs

    def move_pacman(self):
        r, c = self.pacman_pos
        dr, dc = self.pacman_direction

        if self.next_pacman_direction != (0,0):
            next_r, next_c = r + self.next_pacman_direction[0], c + self.next_pacman_direction[1]
            if self.is_valid_move((next_r, next_c)):
                self.pacman_direction = self.next_pacman_direction
                dr, dc = self.pacman_direction
                self.next_pacman_direction = (0,0)

        new_r, new_c = r + dr, c + dc

        if self.is_valid_move((new_r, new_c)):
            self.pacman_pos = (new_r, new_c)
            if (new_r, new_c) in self.dots:
                self.dots.remove((new_r, new_c))
                self.score += 10
                self.score_changed_signal.emit(self.score)
            elif (new_r, new_c) in self.power_pellets:
                self.power_pellets.remove((new_r, new_c))
                self.score += 50
                self.score_changed_signal.emit(self.score)
                self.activate_frightened_mode()
        else:
            self.pacman_direction = (0,0)

    def move_ghosts(self):
        for ghost in self.ghosts:
            if ghost['state'] == EATEN:
                gr, gc = ghost['pos']
                g_dr, g_dc = ghost['direction']
                
                possible_dirs = self.get_possible_directions((gr, gc), (g_dr, g_dc), is_ghost=True, ghost_state=EATEN)
                if possible_dirs:
                    best_dir = possible_dirs[0] if possible_dirs else random.choice([(0,1),(0,-1),(1,0),(-1,0)])
                    ghost['direction'] = best_dir
                    new_gr, new_gc = gr + ghost['direction'][0], gc + ghost['direction'][1]
                    ghost['pos'] = (new_gr, new_gc)
                continue

            gr, gc = ghost['pos']
            g_dr, g_dc = ghost['direction']

            possible_dirs = self.get_possible_directions((gr, gc), (g_dr, g_dc), is_ghost=True, ghost_state=ghost['state'])

            if not possible_dirs:
                ghost['direction'] = (0,0)
                continue

            if len(possible_dirs) > 1 or ghost['direction'] not in possible_dirs:
                target_r, target_c = self.pacman_pos
                best_dir = random.choice(possible_dirs)

                if ghost['state'] == NORMAL:
                    min_dist = float('inf')
                    for dr, dc in possible_dirs:
                        new_gr, new_gc = gr + dr, gc + dc
                        dist = abs(new_gr - target_r) + abs(new_gc - target_c)
                        if dist < min_dist:
                            min_dist = dist
                            best_dir = (dr, dc)
                else:
                    max_dist = -1
                    for dr, dc in possible_dirs:
                        new_gr, new_gc = gr + dr, gc + dc
                        dist = abs(new_gr - target_r) + abs(new_gc - target_c)
                        if dist > max_dist:
                            max_dist = dist
                            best_dir = (dr, dc)
                    if not best_dir and possible_dirs:
                         best_dir = random.choice(possible_dirs)

                ghost['direction'] = best_dir
            
            new_gr, new_gc = gr + ghost['direction'][0], gc + ghost['direction'][1]
            if self.is_valid_move((new_gr, new_gc)):
                ghost['pos'] = (new_gr, new_gc)


    def check_collisions(self):
        pr, pc = self.pacman_pos
        for ghost in self.ghosts:
            gr, gc = ghost['pos']
            if (pr, pc) == (gr, gc):
                if ghost['state'] == NORMAL:
                    self.end_game()
                    return
                elif ghost['state'] == FRIGHTENED:
                    self.score += 200
                    self.score_changed_signal.emit(self.score)
                    ghost['state'] = EATEN
                    
                    valid_regen_spots = [p for p in GHOST_HOUSE_CELLS if self.maze[p[0]][p[1]] == 0]
                    if valid_regen_spots:
                        ghost['pos'] = random.choice(valid_regen_spots)
                    else:
                        ghost['pos'] = ghost['start_pos']
                    
                    ghost['direction'] = (0,0)
                    if ghost['regen_timer']:
                        ghost['regen_timer'].stop()
                    ghost['regen_timer'] = QTimer(self)
                    ghost['regen_timer'].setSingleShot(True)
                    ghost['regen_timer'].timeout.connect(lambda g=ghost: self.regenerate_ghost(g))
                    ghost['regen_timer'].start(GHOST_REGEN_TIME_MS)

    def regenerate_ghost(self, ghost):
        ghost['state'] = NORMAL
        
        exit_r, exit_c = GHOST_HOUSE_EXIT_POINT
        current_r, current_c = ghost['pos']
        
        if current_r == exit_r and current_c == exit_c:
            ghost['direction'] = (-1, 0)
            if not self.is_valid_move((current_r + ghost['direction'][0], current_c + ghost['direction'][1])):
                ghost['direction'] = random.choice([(0,1),(0,-1),(1,0),(-1,0)])
        else:
            if abs(exit_r - current_r) > abs(exit_c - current_c):
                ghost['direction'] = (1 if exit_r > current_r else -1, 0)
            else:
                ghost['direction'] = (0, 1 if exit_c > current_c else -1)
            
            if not self.is_valid_move((current_r + ghost['direction'][0], current_c + ghost['direction'][1])) \
               and (current_r + ghost['direction'][0], current_c + ghost['direction'][1]) != GHOST_HOUSE_EXIT_POINT:
                ghost['direction'] = random.choice([(0, 1), (0, -1), (1, 0), (-1, 0)])

        if ghost['regen_timer']:
            ghost['regen_timer'].stop()
            ghost['regen_timer'] = None

    def activate_frightened_mode(self):
        for ghost in self.ghosts:
            if ghost['state'] == NORMAL:
                ghost['state'] = FRIGHTENED
                ghost['direction'] = (-ghost['direction'][0], -ghost['direction'][1])
                if ghost['direction'] == (0,0):
                    ghost['direction'] = random.choice([(0, 1), (0, -1), (1, 0), (-1, 0)])

        self.frightened_timer.start(FRIGHTENED_DURATION_MS)

    def end_frightened_mode(self):
        for ghost in self.ghosts:
            if ghost['state'] == FRIGHTENED:
                ghost['state'] = NORMAL
        self.update()

    def end_game(self):
        self.game_running = False
        self.game_over = True
        self.game_timer.stop()
        self.frightened_timer.stop()
        for ghost in self.ghosts:
            if ghost['regen_timer']:
                ghost['regen_timer'].stop()
        self.game_over_signal.emit()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        wall_color = QColor("#0000AA")
        painter.setBrush(QBrush(wall_color))
        painter.setPen(Qt.NoPen)
        for r in range(MAZE_ROWS):
            for c in range(MAZE_COLS):
                if self.maze[r][c] == 1:
                    painter.drawRect(c * CELL_SIZE, r * CELL_SIZE, CELL_SIZE, CELL_SIZE)
        
        ghost_house_wall_color = QColor("#8B0000")
        painter.setBrush(QBrush(ghost_house_wall_color))
        painter.setPen(QPen(ghost_house_wall_color.darker(150), 1))

        painter.drawRect(GHOST_HOUSE_RECT_LEFT * CELL_SIZE, GHOST_HOUSE_RECT_TOP * CELL_SIZE,
                         GHOST_HOUSE_RECT_RIGHT * CELL_SIZE - GHOST_HOUSE_RECT_LEFT * CELL_SIZE, CELL_SIZE)
        painter.drawRect(GHOST_HOUSE_RECT_LEFT * CELL_SIZE, GHOST_HOUSE_RECT_BOTTOM * CELL_SIZE - CELL_SIZE,
                         GHOST_HOUSE_RECT_RIGHT * CELL_SIZE - GHOST_HOUSE_RECT_LEFT * CELL_SIZE, CELL_SIZE)
        painter.drawRect(GHOST_HOUSE_RECT_LEFT * CELL_SIZE, GHOST_HOUSE_RECT_TOP * CELL_SIZE,
                         CELL_SIZE, GHOST_HOUSE_RECT_BOTTOM * CELL_SIZE - GHOST_HOUSE_RECT_TOP * CELL_SIZE)
        painter.drawRect(GHOST_HOUSE_RECT_RIGHT * CELL_SIZE - CELL_SIZE, GHOST_HOUSE_RECT_TOP * CELL_SIZE,
                         CELL_SIZE, GHOST_HOUSE_RECT_BOTTOM * CELL_SIZE - GHOST_HOUSE_RECT_TOP * CELL_SIZE)

        painter.setBrush(QBrush(Qt.black))
        painter.setPen(Qt.NoPen)
        painter.drawRect(GHOST_HOUSE_EXIT_POINT[1] * CELL_SIZE, (GHOST_HOUSE_EXIT_POINT[0]) * CELL_SIZE, CELL_SIZE, CELL_SIZE)


        dot_color = QColor("#FFD700")
        painter.setBrush(QBrush(dot_color))
        painter.setPen(Qt.NoPen)
        for r, c in self.dots:
            painter.drawEllipse(c * CELL_SIZE + CELL_SIZE // 2 - 3, r * CELL_SIZE + CELL_SIZE // 2 - 3, 6, 6)

        power_pellet_color = QColor("#FFFFFF")
        painter.setBrush(QBrush(power_pellet_color))
        painter.setPen(Qt.NoPen)
        for r, c in self.power_pellets:
            if int(self.game_timer.remainingTime() / 100) % 2 == 0:
                 painter.drawEllipse(c * CELL_SIZE + CELL_SIZE // 2 - 6, r * CELL_SIZE + CELL_SIZE // 2 - 6, 12, 12)
            else:
                 painter.drawEllipse(c * CELL_SIZE + CELL_SIZE // 2 - 5, r * CELL_SIZE + CELL_SIZE // 2 - 5, 10, 10)

        pr, pc = self.pacman_pos
        pacman_color = QColor("#FFFF00")
        painter.setBrush(QBrush(pacman_color))
        painter.setPen(Qt.NoPen)
        start_angle = 0
        span_angle = 360 * 16

        mouth_open = (int(self.game_timer.remainingTime() / 100) % 2 == 0)
        mouth_angle_offset = 25 if mouth_open else 0

        if self.pacman_direction == (0, 1):
            start_angle = (315 + mouth_angle_offset) * 16
            span_angle = (270 - 2 * mouth_angle_offset) * 16
        elif self.pacman_direction == (0, -1):
            start_angle = (135 + mouth_angle_offset) * 16
            span_angle = (270 - 2 * mouth_angle_offset) * 16
        elif self.pacman_direction == (-1, 0):
            start_angle = (45 + mouth_angle_offset) * 16
            span_angle = (270 - 2 * mouth_angle_offset) * 16
        elif self.pacman_direction == (1, 0):
            start_angle = (225 + mouth_angle_offset) * 16
            span_angle = (270 - 2 * mouth_angle_offset) * 16
        else:
            start_angle = (315) * 16
            span_angle = (270) * 16

        painter.drawPie(pc * CELL_SIZE, pr * CELL_SIZE, CELL_SIZE, CELL_SIZE, start_angle, span_angle)

        for ghost in self.ghosts:
            gr, gc = ghost['pos']
            x, y = gc * CELL_SIZE, gr * CELL_SIZE

            path = QPainterPath()
            path.arcMoveTo(x, y, CELL_SIZE, CELL_SIZE // 2, 0)
            path.arcTo(x, y, CELL_SIZE, CELL_SIZE // 2, 0, 180)
            path.lineTo(x, y + CELL_SIZE)
            
            segment_width = CELL_SIZE / 4
            path.lineTo(x + segment_width, y + CELL_SIZE - CELL_SIZE // 4)
            path.lineTo(x + 2 * segment_width, y + CELL_SIZE)
            path.lineTo(x + 3 * segment_width, y + CELL_SIZE - CELL_SIZE // 4)
            path.lineTo(x + CELL_SIZE, y + CELL_SIZE)
            path.closeSubpath()

            if ghost['state'] == NORMAL:
                painter.setBrush(QBrush(ghost['color']))
                painter.setPen(QPen(ghost['color'].darker(150), 1))
            elif ghost['state'] == FRIGHTENED:
                if int(self.frightened_timer.remainingTime() / 100) % 2 == 0:
                    painter.setBrush(QBrush(QColor("#00008B")))
                else:
                    painter.setBrush(QBrush(QColor("#1E90FF")))
                painter.setPen(QPen(QColor("#0000FF"), 1))
            elif ghost['state'] == EATEN:
                painter.setBrush(QBrush(QColor("#696969")))
                painter.setPen(QPen(QColor("#2F4F4F"), 1))
            
            painter.drawPath(path)

            eye_radius = CELL_SIZE // 6
            eye_offset = CELL_SIZE // 4

            painter.setBrush(QBrush(Qt.white))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(x + eye_offset, y + eye_offset, eye_radius * 2, eye_radius * 2)
            painter.drawEllipse(x + CELL_SIZE - eye_offset - eye_radius * 2, y + eye_offset, eye_radius * 2, eye_radius * 2)

            pupil_color = Qt.black
            if ghost['state'] == FRIGHTENED:
                pupil_color = Qt.white
            elif ghost['state'] == EATEN:
                pupil_color = Qt.red

            pupil_offset_amount = eye_radius // 2
            pupil_dx_offset, pupil_dy_offset = 0, 0
            if ghost['direction'] == (0, 1):
                pupil_dx_offset = pupil_offset_amount
            elif ghost['direction'] == (0, -1):
                pupil_dx_offset = -pupil_offset_amount
            elif ghost['direction'] == (-1, 0):
                pupil_dy_offset = -pupil_offset_amount
            elif ghost['direction'] == (1, 0):
                pupil_dy_offset = pupil_offset_amount
            
            painter.setBrush(QBrush(pupil_color))
            painter.drawEllipse(x + eye_offset + eye_radius - pupil_offset_amount // 2 + pupil_dx_offset,
                                y + eye_offset + eye_radius - pupil_offset_amount // 2 + pupil_dy_offset,
                                pupil_offset_amount, pupil_offset_amount)
            painter.drawEllipse(x + CELL_SIZE - eye_offset - eye_radius - pupil_offset_amount // 2 + pupil_dx_offset,
                                y + eye_offset + eye_radius - pupil_offset_amount // 2 + pupil_dy_offset,
                                pupil_offset_amount, pupil_offset_amount)


        if self.game_over:
            painter.setPen(QPen(QColor("white")))
            painter.setFont(QFont("Arial", 24, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, "GAME OVER!")
            painter.setFont(QFont("Arial", 14))
            painter.drawText(self.rect().adjusted(0, 30, 0, 0), Qt.AlignCenter, "Press 'R' to Restart")
        elif not self.dots and not self.power_pellets and self.game_running:
             painter.setPen(QPen(QColor("white")))
             painter.setFont(QFont("Arial", 24, QFont.Bold))
             painter.drawText(self.rect(), Qt.AlignCenter, "YOU WIN!")
             painter.setFont(QFont("Arial", 14))
             painter.drawText(self.rect().adjusted(0, 30, 0, 0), Qt.AlignCenter, "Press 'R' to Restart")


    def keyPressEvent(self, event):
        key = event.key()

        if self.game_over and key == Qt.Key_R:
            self.parent().restart_game()
            return

        if self.game_running:
            if key == Qt.Key_Up or key == Qt.Key_W:
                self.next_pacman_direction = (-1, 0)
            elif key == Qt.Key_Down or key == Qt.Key_S:
                self.next_pacman_direction = (1, 0)
            elif key == Qt.Key_Left or key == Qt.Key_A:
                self.next_pacman_direction = (0, -1)
            elif key == Qt.Key_Right or key == Qt.Key_D:
                self.next_pacman_direction = (0, 1)

        super().keyPressEvent(event)

class PacmanGameApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.apply_aesthetic()
        self.setup_game_loop()

    def init_ui(self):
        self.setWindowTitle("PyQt5 Pac-Man")
        self.setGeometry(100, 100, WIDTH + 60, HEIGHT + 140)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setAlignment(Qt.AlignCenter)

        self.game_canvas = GameCanvas(self)
        self.game_canvas.game_over_signal.connect(self.handle_game_over)
        self.game_canvas.score_changed_signal.connect(self.update_score_display)
        self.game_canvas.game_win_signal.connect(self.handle_game_win)
        main_layout.addWidget(self.game_canvas, alignment=Qt.AlignCenter)

        self.score_label = QLabel("Score: 0")
        self.score_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.score_label.setStyleSheet("color: #E0E0E0; margin-top: 10px;")
        main_layout.addWidget(self.score_label, alignment=Qt.AlignCenter)

        self.start_restart_button = QPushButton("Start Game")
        self.start_restart_button.setFixedSize(180, 40)
        self.start_restart_button.clicked.connect(self.start_game)
        main_layout.addWidget(self.start_restart_button, alignment=Qt.AlignCenter)

    def setup_game_loop(self):
        self.game_canvas.game_timer.start(GAME_SPEED_MS)

    def start_game(self):
        if not self.game_canvas.game_running:
            self.game_canvas.reset_game()
            self.game_canvas.game_running = True
            self.game_canvas.game_timer.start(GAME_SPEED_MS)
            self.update_score_display()
            self.start_restart_button.setText("Restart Game")
            self.start_restart_button.setStyleSheet(self.get_button_style(True))
            self.game_canvas.setFocus()

    def restart_game(self):
        self.start_game()

    def handle_game_over(self):
        self.game_canvas.game_timer.stop()
        self.start_restart_button.setText("Restart Game")
        self.start_restart_button.setStyleSheet(self.get_button_style(False))
        self.game_canvas.clearFocus()

    def handle_game_win(self):
        self.game_canvas.game_running = False
        self.game_canvas.game_timer.stop()
        self.start_restart_button.setText("Play Again!")
        self.start_restart_button.setStyleSheet(self.get_button_style(False))
        self.game_canvas.clearFocus()
        self.game_canvas.update()

    def update_score_display(self):
        self.score_label.setText(f"Score: {self.game_canvas.score}")

    def apply_aesthetic(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2F4F4F;
                border: 2px solid #555555;
                border-radius: 8px;
            }
            QLabel {
                color: #E0E0E0;
                font-family: 'Arial', sans-serif;
                font-size: 14px;
            }
        """)
        self.start_restart_button.setStyleSheet(self.get_button_style(False))

    def get_button_style(self, active):
        if active:
            return """
                QPushButton {
                    background-color: #28a745;
                    color: white;
                    border: 1px solid #28a745;
                    border-radius: 5px;
                    font-family: 'Arial', sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 8px 15px;
                }
                QPushButton:hover {
                    background-color: #218838;
                }
                QPushButton:pressed {
                    background-color: #1e7e34;
                }
            """
        else:
            return """
                QPushButton {
                    background-color: #007bff;
                    color: white;
                    border: 1px solid #007bff;
                    border-radius: 5px;
                    font-family: 'Arial', sans-serif;
                    font-size: 14px;
                    padding: 8px 15px;
                }
                QPushButton:hover {
                    background-color: #0069d9;
                }
                QPushButton:pressed {
                    background-color: #0062cc;
                }
            """

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = PacmanGameApp()
    ex.show()
    sys.exit(app.exec_())
