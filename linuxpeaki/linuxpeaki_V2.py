import os
import sys
import random
import signal
import math

if "SESSION_MANAGER" in os.environ:
    del os.environ["SESSION_MANAGER"]

from PyQt5.QtCore import Qt, QTimer, QPoint, QElapsedTimer
from PyQt5.QtGui import QPixmap, QTransform, QRegion
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow

# ==========================================
# 설정 값
# ==========================================
IMG_PATH       = "linuxpeaki-transparent.png"
MASCOT_WIDTH   = 250

WALK_SPEED     = 2.25   # 4.5 / 2 (틱이 2배 빨라졌으므로)

GRAVITY        = 0.35   # 0.70 / 2
BOUNCE_DAMPING = 0.55
MIN_BOUNCE_VY  = 3.5   # 2.5 / 2
# ==========================================

S_WALK = "WALK"
S_LOOK = "LOOK"
S_DRAG = "DRAG"
S_FALL = "FALL"


class Spiki(QMainWindow):
    def __init__(self):
        super().__init__()

        self.state     = S_WALK
        self.direction = random.choice([-1, 1])
        self.tick      = 0

        # LOOK
        self.look_ticks_left = 0
        self.look_turns_left = 0

        # DRAG / FALL
        self.drag_offset   = QPoint()
        self.vel_x         = 0.0
        self.vel_y         = 0.0
        self.prev_drag_pos = None
        self.press_timer   = QElapsedTimer()
        self.press_moved   = False

        self.prev_pos      = None   # 이전 틱 위치 (방향 자동 계산용)

        self.init_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_behavior)
        self.timer.start(16)  # ~60Hz

    # ── UI ───────────────────────────────────────────────────────────────
    def init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.label = QLabel(self)
        self.raw_pixmap = QPixmap(IMG_PATH)

        self.screen_geo = QApplication.primaryScreen().geometry()
        init_x = self.screen_geo.width() // 2 - MASCOT_WIDTH // 2
        self.move(init_x, self.floor_y())

        # 좌우 픽스맵 미리 캐시
        base = self.raw_pixmap.scaledToWidth(MASCOT_WIDTH, Qt.SmoothTransformation)
        t_flip = QTransform()
        t_flip.scale(-1, 1)
        self._px_right = base
        self._px_left  = base.transformed(t_flip, Qt.SmoothTransformation)
        self._cur_direction = None   # 마지막으로 렌더링한 방향 캐시

        self.update_image()

    def floor_y(self):
        return self.screen_geo.height() - self.height() - 50

    def update_image(self, flinch=False):
        # 방향과 flinch 모두 변화 없으면 스킵
        if not flinch and self.direction == self._cur_direction:
            return

        pixmap = self._px_left if self.direction == -1 else self._px_right

        if flinch:
            t = QTransform()
            if self.direction == -1:
                t.scale(-1, 1)
            t.scale(1.15, 0.85)
            base = self.raw_pixmap.scaledToWidth(MASCOT_WIDTH, Qt.SmoothTransformation)
            pixmap = base.transformed(t, Qt.SmoothTransformation)

        self.label.setPixmap(pixmap)
        self.label.resize(pixmap.width(), pixmap.height())
        self.resize(pixmap.width(), pixmap.height())
        self.setMask(QRegion(pixmap.mask()))
        self._cur_direction = self.direction

    # ── 상태 전환 ────────────────────────────────────────────────────────
    def enter_walk(self):
        self.state = S_WALK
        # 착지 시 이미 벽에 붙어있으면 방향 보정
        if self.x() <= 0:
            self.direction = 1
        elif self.x() >= self.screen_geo.width() - self.width():
            self.direction = -1
        self.update_image()

    def enter_look(self):
        self.state           = S_LOOK
        self.look_turns_left = random.randint(2, 4)
        self.look_ticks_left = random.randint(30, 90)

    def enter_fall(self, vx=0.0, vy=0.0):
        self.state = S_FALL
        self.vel_x = vx
        self.vel_y = vy
        self.update_image()

    # ── 유틸 ─────────────────────────────────────────────────────────────
    def clamp_x(self, x):
        return max(0, min(x, self.screen_geo.width() - self.width()))

    # ── 메인 루프 ────────────────────────────────────────────────────────
    def update_behavior(self):
        self.tick += 1
        fx    = self.floor_y()
        cur_x = self.x()
        cur_y = self.y()

        # 실제 이동 방향으로 캐릭터 방향 자동 갱신 (WALK/LOOK 제외 — 걷기는 자체 관리)
        if self.prev_pos is not None and self.state in (S_DRAG, S_FALL):
            dx = cur_x - self.prev_pos.x()
            if dx > 2 and self.direction != 1:
                self.direction = 1
                self.update_image()
            elif dx < -2 and self.direction != -1:
                self.direction = -1
                self.update_image()
        self.prev_pos = QPoint(cur_x, cur_y)

        # ── DRAG ─────────────────────────────────────────────────────────
        if self.state == S_DRAG:
            return

        # ── FALL ─────────────────────────────────────────────────────────
        elif self.state == S_FALL:
            self.vel_y += GRAVITY
            next_x = cur_x + self.vel_x
            next_y = cur_y + self.vel_y

            # 벽 반전: 위치가 아닌 속도 방향으로 판정
            # (이미 벽에 붙어있고 그쪽으로 계속 밀리는 경우만 반전)
            if self.vel_x < 0 and cur_x <= 80:
                self.vel_x = abs(self.vel_x) * 0.6
                next_x = cur_x + self.vel_x
            elif self.vel_x > 0 and cur_x >= self.screen_geo.width() - self.width() - 1:
                self.vel_x = -abs(self.vel_x) * 0.6
                next_x = cur_x + self.vel_x
            elif self.vel_y < 0 and cur_y <= 30:
                self.vel_y = abs(self.vel_y) * 0.6
                next_y = cur_y + self.vel_y

            next_x = self.clamp_x(next_x)

            if next_y >= fx:
                next_y = fx
                if abs(self.vel_y) > MIN_BOUNCE_VY:
                    self.vel_y = -self.vel_y * BOUNCE_DAMPING
                    self.vel_x *= 0.75
                else:
                    self.vel_x = 0.0
                    self.vel_y = 0.0
                    self.enter_walk()

            self.move(int(next_x), int(next_y))

        # ── WALK ─────────────────────────────────────────────────────────
        elif self.state == S_WALK:
            if random.random() < 0.0027:
                self.enter_look()
                return

            # 다음 위치가 벽을 넘으면 먼저 방향 전환
            next_x = cur_x + WALK_SPEED * self.direction
            if next_x <= 80 or next_x >= self.screen_geo.width() - self.width():
                self.direction *= -1
                self.update_image()
                next_x = cur_x + WALK_SPEED * self.direction
                # 전환 후에도 벽 안쪽으로 클램프
                next_x = max(0, min(next_x, self.screen_geo.width() - self.width()))

            self.move(int(next_x), fx)

        # ── LOOK ─────────────────────────────────────────────────────────
        elif self.state == S_LOOK:
            self.look_ticks_left -= 1
            if self.look_ticks_left <= 0:
                if self.look_turns_left > 0:
                    self.direction       *= -1
                    self.look_turns_left -= 1
                    self.look_ticks_left  = random.randint(30, 90)
                    self.update_image()
                else:
                    self.enter_walk()
            self.move(cur_x, fx)

    # ── 마우스 이벤트 ────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        self.drag_offset   = event.globalPos() - self.pos()
        self.prev_drag_pos = event.globalPos()
        self.press_moved   = False
        self.vel_x         = 0.0
        self.vel_y         = 0.0
        self.press_timer.start()
        self.state         = S_DRAG

    def mouseMoveEvent(self, event):
        if self.state != S_DRAG:
            return
        new_pos = event.globalPos() - self.drag_offset
        if self.prev_drag_pos is not None:
            dp = event.globalPos() - self.prev_drag_pos
            if math.hypot(dp.x(), dp.y()) > 4:
                self.press_moved = True
            self.vel_x = dp.x() * 2.1
            self.vel_y = dp.y() * 2.7
        self.prev_drag_pos = event.globalPos()
        self.move(new_pos.x(), new_pos.y())

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self.state != S_DRAG:
            self.prev_drag_pos = None
            return

        hold_ms  = self.press_timer.elapsed()
        is_click = (not self.press_moved) and (hold_ms < 300)

        self.prev_drag_pos = None

        if is_click:
            self.enter_walk()   # 클릭만 했으면 그냥 복귀
        else:
            self.enter_fall(vx=self.vel_x, vy=self.vel_y)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv)

    sig_timer = QTimer()
    sig_timer.start(500)
    sig_timer.timeout.connect(lambda: None)

    spiki = Spiki()
    spiki.show()
    sys.exit(app.exec_())
