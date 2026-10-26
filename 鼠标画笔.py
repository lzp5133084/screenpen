# -*- coding: utf-8 -*-
"""
鼠标画笔 ScreenPen
一个可以在任意软件画面上直接书写、标注的 Windows 屏幕画笔。
作者：军哥懂保    微信：xunijiayuan
"""

import os
import sys
import json
import time
import math
import ctypes
import tempfile
import threading
import queue
from ctypes import wintypes
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PyQt5.QtCore import (Qt, QPoint, QPointF, QRect, QRectF, QSize, QTimer,
                          QAbstractNativeEventFilter, pyqtSignal)
from PyQt5.QtGui import (QColor, QPainter, QPen, QBrush, QImage, QPixmap, QFont,
                         QPainterPath, QIcon, QLinearGradient, QPolygonF, QCursor)
from PyQt5.QtWidgets import (QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
                             QGridLayout, QPushButton, QLabel, QSlider, QLineEdit,
                             QListWidget, QListWidgetItem, QFrame, QFileDialog,
                             QInputDialog, QMessageBox, QGraphicsDropShadowEffect,
                             QTextEdit, QSizePolicy)

APP_NAME = "鼠标画笔"
APP_EN = "ScreenPen"
VERSION = "1.0.0"
AUTHOR = "军哥懂保"
WECHAT = "xunijiayuan"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_DIR = os.path.join(BASE_DIR, "截图存档")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
HISTORY_PATH = os.path.join(BASE_DIR, "history.json")

# ---------------------------------------------------------------- 工具定义
TOOLS = [
    ("pen", "画笔", "自由书写，跟随鼠标画线"),
    ("hl", "荧光笔", "半透明粗线，像马克笔做高亮"),
    ("line", "直线", "拖拽画出笔直的线"),
    ("arrow", "箭头", "带箭头的指示线"),
    ("rect", "矩形", "框选重点内容"),
    ("ellipse", "椭圆", "圈出重点内容"),
    ("text", "文字", "点击位置输入文字"),
    ("eraser", "橡皮", "只擦除笔迹，不擦屏幕"),
]
TOOL_MAP = {t[0]: t for t in TOOLS}
SHAPE_TOOLS = {"line", "arrow", "rect", "ellipse"}
FREE_TOOLS = {"pen", "hl", "eraser"}

COLORS = ["#E8C87A", "#FF4D5E", "#FF9F45", "#3DDC97",
          "#38E1E8", "#4C8DFF", "#B57BFF", "#FFFFFF"]

TERMS = [
    ("穿透模式", "画笔层变成透明的，鼠标点击会\"穿过去\"，直接操作下面的软件；"
                 "你画在屏幕上的笔迹还留着，不会消失。"),
    ("绘画模式", "鼠标被画笔层接管，拖动鼠标就是画画，下面的软件暂时不会被点到。"),
    ("荧光笔", "半透明的粗线，像用马克笔在屏幕上划重点，下面的内容还看得见。"),
    ("橡皮", "只擦掉你自己画的笔迹，不会擦掉屏幕上原本的内容。"),
    ("撤销 / 重做", "撤销是退回上一笔，重做是再往前一步。程序会把每一步都记住。"),
    ("虚拟桌面", "多显示器时，程序把所有屏幕拼成一整张大画布，可以在任何一块屏上画。"),
    ("合成截图", "把\"屏幕原本的画面\"和\"你画的笔迹\"合并成一张图保存下来。"),
    ("本地接口", "程序在本机开放一个小端口，其他程序可以通过这个端口指挥画笔（开关、清空、截图）。"),
    ("存档", "每次保存的截图都会记一条记录，可以随时在\"存档\"里找到并打开。"),
]


# ---------------------------------------------------------------- 通用函数
def fmt_size(num):
    num = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            if unit == "B":
                return "%d %s" % (int(num), unit)
            return "%.1f %s" % (num, unit)
        num /= 1024.0
    return "%.1f GB" % num


def project_size():
    total = 0
    for dirpath, dirnames, filenames in os.walk(BASE_DIR):
        if os.path.abspath(dirpath).startswith(os.path.abspath(ARCHIVE_DIR)):
            continue
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return total


def fmt_mtime():
    try:
        ts = os.path.getmtime(os.path.abspath(__file__))
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return "未知"


def virtual_geometry():
    geo = QRect()
    for screen in QApplication.screens():
        geo = geo.united(screen.geometry())
    if geo.isNull():
        geo = QRect(0, 0, 1280, 720)
    return geo


def make_cross_cursor(color="#E8C87A"):
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    c = QColor(color)
    p.setPen(QPen(QColor(0, 0, 0, 120), 4))
    p.drawLine(16, 2, 16, 30)
    p.drawLine(2, 16, 30, 16)
    p.setPen(QPen(c, 2))
    p.drawLine(16, 3, 16, 29)
    p.drawLine(3, 16, 29, 16)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(c, 1.4))
    p.drawEllipse(QPointF(16, 16), 5, 5)
    p.end()
    return QCursor(pm, 16, 16)


# ---------------------------------------------------------------- 配置
class Config(object):
    DEFAULTS = {
        "tool": "pen",
        "color": "#E8C87A",
        "width": 4,
        "panel_pos": None,
        "ball_pos": None,
        "start_through": False,
        "collapsed": False,
    }

    def __init__(self, path):
        self.path = path
        self.data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                for key in self.DEFAULTS:
                    if key in raw:
                        self.data[key] = raw[key]
        except (IOError, OSError, ValueError):
            pass

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except (IOError, OSError):
            pass

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value, save=True):
        self.data[key] = value
        if save:
            self.save()


# ---------------------------------------------------------------- 存档记录
class Archive(object):
    def __init__(self, path):
        self.path = path
        self.items = []
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                self.items = raw
        except (IOError, OSError, ValueError):
            self.items = []

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.items, f, ensure_ascii=False, indent=2)
        except (IOError, OSError):
            pass

    def add(self, path, strokes, tools):
        self.items.insert(0, {
            "file": path,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "strokes": strokes,
            "tools": tools,
        })
        self.items = self.items[:100]
        self.save()

    def remove(self, index, delete_file=True):
        if 0 <= index < len(self.items):
            item = self.items.pop(index)
            self.save()
            if delete_file:
                try:
                    if os.path.exists(item.get("file", "")):
                        os.remove(item["file"])
                except OSError:
                    pass
        self.save()

    def clear(self, delete_file=True):
        if delete_file:
            for item in self.items:
                try:
                    if os.path.exists(item.get("file", "")):
                        os.remove(item["file"])
                except OSError:
                    pass
        self.items = []
        self.save()


# ---------------------------------------------------------------- 图标绘制
def tool_icon(tool, color, size=40):
    pm = QPixmap(size, size)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    w = size / 2.0
    c = QColor(color)
    pen = QPen(c, max(1.6, w / 12.0))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if tool == "pen":
        p.drawLine(QPointF(w * 0.28, w * 0.72), QPointF(w * 0.62, w * 0.80))
        p.drawLine(QPointF(w * 0.34, w * 0.66), QPointF(w * 0.70, w * 0.30))
        p.setBrush(c)
        p.drawPolygon(QPolygonF([QPointF(w * 0.72, w * 0.28),
                                 QPointF(w * 0.86, w * 0.18),
                                 QPointF(w * 0.80, w * 0.36)]))
    elif tool == "hl":
        p.setPen(QPen(QColor(c.red(), c.green(), c.blue(), 110), w * 0.34, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(w * 0.28, w * 0.72), QPointF(w * 0.72, w * 0.28))
    elif tool == "line":
        p.drawLine(QPointF(w * 0.26, w * 0.74), QPointF(w * 0.74, w * 0.26))
    elif tool == "arrow":
        p.drawLine(QPointF(w * 0.26, w * 0.74), QPointF(w * 0.74, w * 0.26))
        p.setBrush(c)
        p.drawPolygon(QPolygonF([QPointF(w * 0.78, w * 0.22),
                                 QPointF(w * 0.52, w * 0.30),
                                 QPointF(w * 0.70, w * 0.48)]))
    elif tool == "rect":
        p.drawRoundedRect(QRectF(w * 0.24, w * 0.30, w * 0.52, w * 0.40), 3, 3)
    elif tool == "ellipse":
        p.drawEllipse(QRectF(w * 0.22, w * 0.30, w * 0.56, w * 0.40))
    elif tool == "text":
        f = QFont("Microsoft YaHei", int(w * 0.62))
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 0, w, w), Qt.AlignCenter, "T")
    elif tool == "eraser":
        path = QPainterPath()
        path.moveTo(w * 0.30, w * 0.62)
        path.lineTo(w * 0.56, w * 0.28)
        path.lineTo(w * 0.78, w * 0.46)
        path.lineTo(w * 0.54, w * 0.74)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(w * 0.26, w * 0.80), QPointF(w * 0.76, w * 0.80))
    p.end()
    return QIcon(pm)


def mini_icon(kind, color="#C9CDD6", size=32):
    pm = QPixmap(size, size)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    w = size / 2.0
    c = QColor(color)
    p.setPen(QPen(c, 1.7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    if kind == "undo":
        path = QPainterPath()
        path.moveTo(w * 0.32, w * 0.40)
        path.lineTo(w * 0.68, w * 0.40)
        path.cubicTo(w * 0.88, w * 0.40, w * 0.88, w * 0.70, w * 0.64, w * 0.70)
        path.lineTo(w * 0.46, w * 0.70)
        p.drawPath(path)
        p.drawPolyline(QPolygonF([QPointF(w * 0.44, w * 0.28), QPointF(w * 0.30, w * 0.40),
                                  QPointF(w * 0.44, w * 0.52)]))
    elif kind == "redo":
        path = QPainterPath()
        path.moveTo(w * 0.68, w * 0.40)
        path.lineTo(w * 0.32, w * 0.40)
        path.cubicTo(w * 0.12, w * 0.40, w * 0.12, w * 0.70, w * 0.36, w * 0.70)
        path.lineTo(w * 0.54, w * 0.70)
        p.drawPath(path)
        p.drawPolyline(QPolygonF([QPointF(w * 0.56, w * 0.28), QPointF(w * 0.70, w * 0.40),
                                  QPointF(w * 0.56, w * 0.52)]))
    elif kind == "trash":
        p.drawLine(QPointF(w * 0.28, w * 0.36), QPointF(w * 0.72, w * 0.36))
        p.drawLine(QPointF(w * 0.40, w * 0.28), QPointF(w * 0.60, w * 0.28))
        p.drawPolyline(QPolygonF([QPointF(w * 0.36, w * 0.40), QPointF(w * 0.40, w * 0.74),
                                  QPointF(w * 0.62, w * 0.74), QPointF(w * 0.66, w * 0.40)]))
    elif kind == "save":
        p.drawRoundedRect(QRectF(w * 0.26, w * 0.26, w * 0.48, w * 0.48), 2, 2)
        p.drawRect(QRectF(w * 0.38, w * 0.26, w * 0.24, w * 0.16))
        p.drawRect(QRectF(w * 0.36, w * 0.54, w * 0.28, w * 0.20))
    elif kind == "archive":
        p.drawRoundedRect(QRectF(w * 0.24, w * 0.34, w * 0.52, w * 0.40), 2, 2)
        p.drawLine(QPointF(w * 0.24, w * 0.46), QPointF(w * 0.76, w * 0.46))
        p.drawLine(QPointF(w * 0.40, w * 0.28), QPointF(w * 0.60, w * 0.28))
    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------- 画笔层
class Board(QWidget):
    """覆盖整个虚拟桌面的透明画笔层。"""

    def __init__(self, ctrl):
        super(Board, self).__init__(None)
        self.ctrl = ctrl
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                            Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        geo = virtual_geometry()
        self.setGeometry(geo)
        self.image = QImage(geo.size(), QImage.Format_ARGB32_Premultiplied)
        self.image.fill(Qt.transparent)

        self.strokes = []
        self.redo_stack = []
        self.current = None
        self.preview_rect = QRect()
        self.last_pos = QPoint()
        self.setCursor(make_cross_cursor())

    # -------------------------------------------------- 模式
    def apply_click_through(self, enable):
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            get_long.argtypes = [wintypes.HWND, ctypes.c_int]
            get_long.restype = ctypes.c_longlong
            set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong]
            set_long.restype = ctypes.c_longlong
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOOLWINDOW = 0x00000080
            style = get_long(hwnd, GWL_EXSTYLE)
            if enable:
                style |= (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW)
            else:
                style = (style | WS_EX_LAYERED) & ~WS_EX_TRANSPARENT
            set_long(hwnd, GWL_EXSTYLE, style)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, enable)
        except Exception:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, enable)

    def refresh_geometry(self):
        geo = virtual_geometry()
        if geo.size() != self.image.size():
            self.setGeometry(geo)
            self.image = QImage(geo.size(), QImage.Format_ARGB32_Premultiplied)
            self.image.fill(Qt.transparent)
            self.rebuild()
        self.update()

    # -------------------------------------------------- 绘制核心
    def _stroke_pen(self, stroke):
        tool = stroke["tool"]
        color = QColor(stroke["color"])
        width = stroke["width"]
        if tool == "hl":
            c = QColor(color)
            c.setAlpha(72)
            return QPen(c, max(6.0, width * 3.6), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        if tool == "eraser":
            return QPen(QColor(0, 0, 0), max(6.0, width * 2.0), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        pen = QPen(color, max(1.0, width), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        return pen

    def draw_stroke(self, painter, stroke):
        tool = stroke["tool"]
        pts = stroke["points"]
        if not pts:
            return
        painter.setRenderHint(QPainter.Antialiasing, True)
        if tool == "eraser":
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
        else:
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        pen = self._stroke_pen(stroke)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        if tool in FREE_TOOLS:
            if len(pts) == 1:
                radius = pen.width() / 2.0
                painter.setPen(Qt.NoPen)
                painter.setBrush(pen.color())
                painter.drawEllipse(QPointF(pts[0]), radius, radius)
            for i in range(1, len(pts)):
                painter.drawLine(pts[i - 1], pts[i])
        elif tool in SHAPE_TOOLS:
            p1, p2 = pts[0], pts[-1]
            if tool == "line":
                painter.drawLine(p1, p2)
            elif tool == "rect":
                painter.drawRect(QRect(p1, p2).normalized())
            elif tool == "ellipse":
                painter.drawEllipse(QRect(p1, p2).normalized())
            elif tool == "arrow":
                self.draw_arrow(painter, p1, p2, pen)
        elif tool == "text":
            text = stroke.get("text", "")
            if text:
                size = max(16, int(stroke["width"] * 6))
                font = QFont("Microsoft YaHei", size)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QPen(QColor(stroke["color"])))
                painter.drawText(pts[0], text)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

    def draw_arrow(self, painter, p1, p2, pen):
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.hypot(dx, dy)
        if length < 1:
            return
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(p1, p2)
        head = min(max(14.0, pen.width() * 5.0), length * 0.45)
        angle = math.atan2(dy, dx)
        left = QPointF(p2.x() - head * math.cos(angle - 0.42),
                       p2.y() - head * math.sin(angle - 0.42))
        right = QPointF(p2.x() - head * math.cos(angle + 0.42),
                        p2.y() - head * math.sin(angle + 0.42))
        painter.setPen(Qt.NoPen)
        painter.setBrush(pen.color())
        painter.drawPolygon(QPolygonF([QPointF(p2), left, right]))

    def stroke_bbox(self, stroke):
        pts = stroke["points"]
        if not pts:
            return QRect()
        tool = stroke["tool"]
        w = stroke["width"]
        pad = int(max(8, w * 4))
        if tool == "text":
            return QRect(pts[0].x() - 8, pts[0].y() - 8,
                         max(120, int(w * 6 * 12)), max(40, int(w * 6 * 1.6)))
        if tool in ("hl", "eraser"):
            pad = int(max(10, w * 5))
        rect = QRect(pts[0], pts[0])
        for p in pts[1:]:
            rect = rect.united(QRect(p, p))
        return rect.adjusted(-pad, -pad, pad, pad)

    def rebuild(self):
        self.image.fill(Qt.transparent)
        painter = QPainter(self.image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        for stroke in self.strokes:
            self.draw_stroke(painter, stroke)
        painter.end()

    # -------------------------------------------------- 鼠标事件
    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.ctrl.toggle_mode()
            return
        if event.button() != Qt.LeftButton:
            return
        tool = self.ctrl.tool
        pos = event.pos()
        self.last_pos = pos
        self.current = {
            "tool": tool,
            "points": [pos],
            "color": self.ctrl.color,
            "width": self.ctrl.width,
            "text": "",
        }
        self.preview_rect = QRect()
        if tool in FREE_TOOLS:
            painter = QPainter(self.image)
            self.draw_stroke(painter, self.current)
            painter.end()
            r = self.stroke_bbox(self.current)
            self.update(r)

    def mouseMoveEvent(self, event):
        if self.current is None:
            return
        tool = self.current["tool"]
        pos = event.pos()
        if tool in FREE_TOOLS:
            if (pos - self.last_pos).manhattanLength() < 2:
                return
            prev = self.current["points"][-1]
            self.current["points"].append(pos)
            painter = QPainter(self.image)
            self._paint_segment(painter, self.current, prev, pos)
            painter.end()
            self.last_pos = pos
            r = QRect(prev, pos).normalized().adjusted(-20, -20, 20, 20)
            self.update(r)
        elif tool in SHAPE_TOOLS:
            self.current["points"] = [self.current["points"][0], pos]
            new_rect = self.stroke_bbox(self.current)
            self.update(new_rect.united(self.preview_rect))
            self.preview_rect = new_rect

    def _paint_segment(self, painter, stroke, p1, p2):
        tool = stroke["tool"]
        painter.setRenderHint(QPainter.Antialiasing, True)
        if tool == "eraser":
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
        else:
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        pen = self._stroke_pen(stroke)
        painter.setPen(pen)
        painter.drawLine(p1, p2)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self.current is None:
            return
        stroke = self.current
        self.current = None
        tool = stroke["tool"]

        if tool == "text":
            text, ok = QInputDialog.getText(None, "输入文字", "请输入要标注的文字：")
            if not ok or not text.strip():
                return
            stroke["text"] = text.strip()
            self.strokes.append(stroke)
            self.redo_stack = []
            painter = QPainter(self.image)
            self.draw_stroke(painter, stroke)
            painter.end()
            self.update(self.stroke_bbox(stroke))
            self.ctrl.notify("已添加文字标注")
            return

        self.strokes.append(stroke)
        self.redo_stack = []
        if tool in SHAPE_TOOLS:
            painter = QPainter(self.image)
            self.draw_stroke(painter, stroke)
            painter.end()
            self.update(self.stroke_bbox(stroke))
        self.ctrl.on_stroke_done()

    def wheelEvent(self, event):
        delta = 1 if event.angleDelta().y() > 0 else -1
        self.ctrl.change_width(delta)
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawImage(0, 0, self.image)
        if self.current is not None and self.current["tool"] in SHAPE_TOOLS:
            self.draw_stroke(painter, self.current)
        painter.end()

    # -------------------------------------------------- 撤销 / 重做 / 清空
    def undo(self):
        if not self.strokes:
            self.ctrl.notify("没有可以撤销的笔迹")
            return False
        self.redo_stack.append(self.strokes.pop())
        self.rebuild()
        self.update()
        self.ctrl.notify("已撤销一步")
        return True

    def redo(self):
        if not self.redo_stack:
            self.ctrl.notify("没有可以重做的笔迹")
            return False
        stroke = self.redo_stack.pop()
        self.strokes.append(stroke)
        painter = QPainter(self.image)
        self.draw_stroke(painter, stroke)
        painter.end()
        self.update(self.stroke_bbox(stroke))
        self.ctrl.notify("已重做一步")
        return True

    def clear(self):
        self.strokes = []
        self.redo_stack = []
        self.current = None
        self.image.fill(Qt.transparent)
        self.update()
        self.ctrl.notify("画布已清空")


# ---------------------------------------------------------------- 控制面板
STYLE = """
QLabel { color: #E9E9EE; font-family: "Microsoft YaHei"; }
QLabel#Title { font-size: 15px; font-weight: 700; color: #F4E7C6; letter-spacing: 1px; }
QLabel#Ver { font-size: 9px; color: #7E8390; }
QLabel#Section { font-size: 9px; color: #6E7480; letter-spacing: 2px; }
QLabel#Info { font-size: 9px; color: #656B77; }
QLabel#Meta { font-size: 9px; color: #5C626E; }
QLabel#Hint { font-size: 10px; color: #B8BEC9; }
QLabel#Pill, QPushButton#Pill { font-size: 9px; font-weight: 700; border-radius: 9px; }
QPushButton#Pill { padding: 3px 9px; }
QLabel#Pill[mode="paint"], QPushButton#Pill[mode="paint"] {
    background: #E8C87A; color: #13151B; border: none; }
QLabel#Pill[mode="through"], QPushButton#Pill[mode="through"] {
    background: rgba(79,209,197,0.14); color: #4FD1C5;
    border: 1px solid rgba(79,209,197,0.42); }
QPushButton#Tool { background: rgba(255,255,255,0.035); border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px; }
QPushButton#Tool:hover { background: rgba(232,200,122,0.10); border: 1px solid rgba(232,200,122,0.35); }
QPushButton#Tool[active="true"] { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
    stop:0 #F5E0A8, stop:1 #D6AE56); border: 1px solid #F7E8BE; }
QPushButton#Act { background: rgba(255,255,255,0.045); border: 1px solid rgba(255,255,255,0.07);
    border-radius: 9px; color: #C6CBD5; font-size: 11px; padding: 6px 0; }
QPushButton#Act:hover { background: rgba(232,200,122,0.13); color: #F4E5BC;
    border-color: rgba(232,200,122,0.38); }
QPushButton#Act:disabled { color: #4A4F59; background: rgba(255,255,255,0.02); }
QPushButton#Ghost { background: transparent; border: none; color: #8A8F9A; font-size: 12px;
    font-weight: 700; }
QPushButton#Ghost:hover { color: #E8C87A; }
QPushButton#Swatch { border-radius: 9px; border: 1px solid rgba(255,255,255,0.25); }
QPushButton#Swatch[active="true"] { border: 2px solid #FFFFFF; }
QSlider::groove:horizontal { height: 3px; background: rgba(255,255,255,0.10); border-radius: 2px; }
QSlider::sub-page:horizontal { background: #E8C87A; border-radius: 2px; }
QSlider::handle:horizontal { width: 12px; height: 12px; margin: -5px 0; border-radius: 6px;
    background: #F7E8BE; border: 1px solid #B99248; }
QLineEdit { background: rgba(255,255,255,0.05); border: 1px solid rgba(232,200,122,0.3);
    border-radius: 8px; color: #EDEDF0; padding: 6px 9px; font-size: 12px; }
QListWidget { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px; color: #D6DAE2; font-size: 11px; }
QListWidget::item { padding: 7px 6px; border-bottom: 1px solid rgba(255,255,255,0.04); }
QListWidget::item:selected { background: rgba(232,200,122,0.16); color: #F4E5BC; }
QTextEdit { background: transparent; border: none; color: #C9CED8; font-size: 11px; }
QScrollBar:vertical { background: transparent; width: 6px; }
QScrollBar::handle:vertical { background: rgba(232,200,122,0.35); border-radius: 3px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


class Panel(QWidget):
    WIDTH = 300

    def __init__(self, ctrl):
        super(Panel, self).__init__(None)
        self.ctrl = ctrl
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(self.WIDTH)
        self.setStyleSheet(STYLE)
        self._drag_offset = None
        self._build()
        self.refresh_meta()
        self.refresh_state()

    # -------------------------------------------------- UI
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)

        self.card = QFrame(self)
        self.card.setObjectName("Card")
        outer.addWidget(self.card)

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(9)

        # 标题行
        head = QHBoxLayout()
        head.setSpacing(8)
        dot = QLabel("●")
        dot.setStyleSheet("color:#E8C87A; font-size:12px;")
        head.addWidget(dot)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel(APP_NAME)
        title.setObjectName("Title")
        ver = QLabel("%s v%s" % (APP_EN, VERSION))
        ver.setObjectName("Ver")
        title_box.addWidget(title)
        title_box.addWidget(ver)
        head.addLayout(title_box)
        head.addStretch(1)
        self.pill = QPushButton("绘画中")
        self.pill.setObjectName("Pill")
        self.pill.setProperty("mode", "paint")
        self.pill.setCursor(Qt.PointingHandCursor)
        self.pill.setToolTip("单击切换 绘画 / 穿透（Ctrl+Alt+D）")
        self.pill.clicked.connect(self.ctrl.toggle_mode)
        head.addWidget(self.pill)
        btn_min = QPushButton("—")
        btn_min.setObjectName("Ghost")
        btn_min.setFixedSize(20, 20)
        btn_min.setToolTip("收起为悬浮球")
        btn_min.clicked.connect(self.ctrl.collapse_panel)
        btn_close = QPushButton("×")
        btn_close.setObjectName("Ghost")
        btn_close.setFixedSize(20, 20)
        btn_close.setToolTip("退出程序")
        btn_close.clicked.connect(self.ctrl.quit_app)
        head.addWidget(btn_min)
        head.addWidget(btn_close)
        lay.addLayout(head)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.055);")
        lay.addWidget(sep)

        # 工具区
        lab1 = QLabel("画 笔 工 具")
        lab1.setObjectName("Section")
        lay.addWidget(lab1)

        grid = QGridLayout()
        grid.setSpacing(6)
        self.tool_buttons = {}
        for index, (key, name, tip) in enumerate(TOOLS):
            btn = QPushButton()
            btn.setObjectName("Tool")
            btn.setFixedHeight(46)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip("%s — %s" % (name, tip))
            btn.setIconSize(QSize(20, 20))
            btn.setProperty("active", "false")
            btn.clicked.connect(lambda checked=False, k=key: self.ctrl.set_tool(k))
            grid.addWidget(btn, index // 4, index % 4)
            self.tool_buttons[key] = (btn, name)
        lay.addLayout(grid)

        # 颜色
        row = QHBoxLayout()
        lab2 = QLabel("颜 色")
        lab2.setObjectName("Section")
        row.addWidget(lab2)
        row.addStretch(1)
        self.swatches = []
        for color in COLORS:
            sw = QPushButton()
            sw.setObjectName("Swatch")
            sw.setFixedSize(18, 18)
            sw.setCursor(Qt.PointingHandCursor)
            sw.setProperty("active", "false")
            sw.setStyleSheet("QPushButton#Swatch{background:%s;border-radius:9px;"
                             "border:1px solid rgba(255,255,255,0.22);}"
                             "QPushButton#Swatch:hover{border:2px solid #fff;}" % color)
            sw.clicked.connect(lambda checked=False, c=color: self.ctrl.set_color(c))
            row.addWidget(sw)
            self.swatches.append((color, sw))
        lay.addLayout(row)

        # 线宽
        width_row = QHBoxLayout()
        lab3 = QLabel("笔 宽")
        lab3.setObjectName("Section")
        width_row.addWidget(lab3)
        self.width_slider = QSlider(Qt.Horizontal)
        self.width_slider.setRange(1, 40)
        self.width_slider.valueChanged.connect(self.ctrl.set_width)
        width_row.addWidget(self.width_slider, 1)
        self.width_label = QLabel("4")
        self.width_label.setFixedWidth(22)
        self.width_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.width_label.setStyleSheet("color:#E8C87A; font-size:11px; font-weight:700;")
        width_row.addWidget(self.width_label)
        lay.addLayout(width_row)

        # 主操作
        act = QGridLayout()
        act.setSpacing(6)
        self.btn_undo = QPushButton("  撤销")
        self.btn_undo.setObjectName("Act")
        self.btn_undo.setIcon(mini_icon("undo"))
        self.btn_undo.setCursor(Qt.PointingHandCursor)
        self.btn_undo.clicked.connect(self.ctrl.undo)
        self.btn_redo = QPushButton("  重做")
        self.btn_redo.setObjectName("Act")
        self.btn_redo.setIcon(mini_icon("redo"))
        self.btn_redo.setCursor(Qt.PointingHandCursor)
        self.btn_redo.clicked.connect(self.ctrl.redo)
        self.btn_clear = QPushButton("  清空")
        self.btn_clear.setObjectName("Act")
        self.btn_clear.setIcon(mini_icon("trash", "#FF8A97"))
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.clicked.connect(self.ctrl.clear_all)
        self.btn_save = QPushButton("  截图")
        self.btn_save.setObjectName("Act")
        self.btn_save.setIcon(mini_icon("save", "#E8C87A"))
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setToolTip("把屏幕和笔迹合成保存")
        self.btn_save.clicked.connect(self.ctrl.save_shot)
        act.addWidget(self.btn_undo, 0, 0)
        act.addWidget(self.btn_redo, 0, 1)
        act.addWidget(self.btn_clear, 0, 2)
        act.addWidget(self.btn_save, 0, 3)
        lay.addLayout(act)

        # 次级操作
        act2 = QGridLayout()
        act2.setSpacing(6)
        btn_arch = QPushButton("  存档")
        btn_arch.setObjectName("Act")
        btn_arch.setIcon(mini_icon("archive"))
        btn_arch.setCursor(Qt.PointingHandCursor)
        btn_arch.clicked.connect(self.ctrl.open_archive)
        btn_help = QPushButton("  说明")
        btn_help.setObjectName("Act")
        btn_help.setCursor(Qt.PointingHandCursor)
        btn_help.clicked.connect(self.ctrl.open_help)
        btn_about = QPushButton("  关于")
        btn_about.setObjectName("Act")
        btn_about.setCursor(Qt.PointingHandCursor)
        btn_about.clicked.connect(self.ctrl.open_about)
        act2.addWidget(btn_arch, 0, 0)
        act2.addWidget(btn_help, 0, 1)
        act2.addWidget(btn_about, 0, 2)
        lay.addLayout(act2)

        # 提示条
        self.hint = QLabel("快捷键 Ctrl+Alt+D 切换绘画 / 穿透")
        self.hint.setObjectName("Hint")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)

        # 信息区
        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background: rgba(255,255,255,0.055);")
        lay.addWidget(sep2)

        self.meta = QLabel()
        self.meta.setObjectName("Meta")
        self.meta.setWordWrap(True)
        lay.addWidget(self.meta)

        foot = QLabel("%s · 微信 %s" % (AUTHOR, WECHAT))
        foot.setObjectName("Info")
        lay.addWidget(foot)

        self.adjustSize()

    # -------------------------------------------------- 背景
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.card.geometry()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0.0, QColor(22, 24, 31, 249))
        grad.setColorAt(0.55, QColor(14, 15, 20, 251))
        grad.setColorAt(1.0, QColor(9, 10, 14, 253))
        painter.fillPath(path, QBrush(grad))
        painter.setPen(QPen(QColor(232, 200, 122, 55), 1))
        painter.drawPath(path)
        # 顶部金色细光
        painter.setPen(QPen(QColor(232, 200, 122, 120), 1))
        painter.drawLine(QPointF(rect.left() + 22, rect.top() + 1),
                         QPointF(rect.right() - 22, rect.top() + 1))
        painter.end()

    # -------------------------------------------------- 刷新
    def refresh_state(self):
        ctrl = self.ctrl
        for key, (btn, name) in self.tool_buttons.items():
            active = key == ctrl.tool
            btn.setProperty("active", "true" if active else "false")
            btn.setText(name if active else "")
            btn.setIcon(tool_icon(key, "#171A21" if active else "#D5D9E1"))
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        for color, sw in self.swatches:
            active = color.lower() == ctrl.color.lower()
            sw.setProperty("active", "true" if active else "false")
            sw.style().unpolish(sw)
            sw.style().polish(sw)
        if self.width_slider.value() != ctrl.width:
            self.width_slider.blockSignals(True)
            self.width_slider.setValue(ctrl.width)
            self.width_slider.blockSignals(False)
        self.width_label.setText(str(ctrl.width))
        if ctrl.paint_mode:
            self.pill.setText("绘画中")
            self.pill.setProperty("mode", "paint")
        else:
            self.pill.setText("穿透中")
            self.pill.setProperty("mode", "through")
        self.pill.style().unpolish(self.pill)
        self.pill.style().polish(self.pill)
        self.btn_undo.setEnabled(len(ctrl.board.strokes) > 0)
        self.btn_redo.setEnabled(len(ctrl.board.redo_stack) > 0)

    def refresh_meta(self):
        size_text = fmt_size(project_size())
        self.meta.setText("程序大小 %s · 最后修改 %s\n当前版本 v%s · 共 %d 个工具"
                          % (size_text, fmt_mtime(), VERSION, len(TOOLS)))

    def notify(self, text):
        self.hint.setText(text)

    # -------------------------------------------------- 拖动
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_offset is not None:
            self._drag_offset = None
            self.ctrl.save_panel_pos()
            event.accept()


# ---------------------------------------------------------------- 悬浮球
class DockBall(QWidget):
    def __init__(self, ctrl):
        super(DockBall, self).__init__(None)
        self.ctrl = ctrl
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(58, 58)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("单击展开鼠标画笔")
        self._press = None
        self._moved = False

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(4, 4, 50, 50)
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0, QColor(245, 224, 168))
        grad.setColorAt(1, QColor(198, 158, 74))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(255, 244, 214, 170), 1.4))
        p.drawEllipse(rect)
        p.setPen(QPen(QColor(26, 22, 14, 220), 2.2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(22, 38), QPointF(36, 24))
        p.setBrush(QColor(26, 22, 14, 220))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(38, 22), QPointF(42, 22), QPointF(42, 26)]))
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press = event.globalPos()
            self._moved = False

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & Qt.LeftButton:
            if (event.globalPos() - self._press).manhattanLength() > 4:
                self._moved = True
            self.move(event.globalPos() - QPoint(29, 29))

    def mouseReleaseEvent(self, event):
        if self._press is None:
            return
        self._press = None
        if not self._moved:
            self.ctrl.expand_panel()
        else:
            self.ctrl.save_ball_pos()


# ---------------------------------------------------------------- 对话框
def dialog_frame(parent=None):
    dlg = QDialog(parent)
    dlg.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
    dlg.setAttribute(Qt.WA_TranslucentBackground, True)
    dlg.setStyleSheet(STYLE)
    outer = QVBoxLayout(dlg)
    outer.setContentsMargins(20, 20, 20, 20)
    card = QFrame()
    shadow = QGraphicsDropShadowEffect(dlg)
    shadow.setBlurRadius(18)
    shadow.setOffset(0, 5)
    shadow.setColor(QColor(0, 0, 0, 200))
    card.setGraphicsEffect(shadow)
    card.setStyleSheet("QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                       "stop:0 rgba(22,24,31,250), stop:1 rgba(9,10,14,252));"
                       "border:1px solid rgba(232,200,122,0.22); border-radius:16px;}")
    outer.addWidget(card)
    inner = QVBoxLayout(card)
    inner.setContentsMargins(20, 16, 20, 16)
    inner.setSpacing(10)
    dlg.card_layout = inner
    return dlg


def dlg_header(dlg, title, subtitle="", with_terms=False):
    lay = dlg.card_layout
    row = QHBoxLayout()
    box = QVBoxLayout()
    box.setSpacing(2)
    lab = QLabel(title)
    lab.setObjectName("Title")
    box.addWidget(lab)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("Ver")
        box.addWidget(sub)
    row.addLayout(box)
    row.addStretch(1)
    if with_terms:
        btn = QPushButton("?")
        btn.setFixedSize(22, 22)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip("名词解释")
        btn.setStyleSheet("QPushButton{background:rgba(232,200,122,0.14); color:#E8C87A;"
                          "border:1px solid rgba(232,200,122,0.45); border-radius:11px;"
                          "font-size:11px; font-weight:700;}"
                          "QPushButton:hover{background:rgba(232,200,122,0.26);}")
        btn.clicked.connect(lambda: show_terms(dlg))
        row.addWidget(btn)
    close = QPushButton("×")
    close.setObjectName("Ghost")
    close.setFixedSize(22, 22)
    close.clicked.connect(dlg.accept)
    row.addWidget(close)
    lay.addLayout(row)
    sep = QFrame()
    sep.setFixedHeight(1)
    sep.setStyleSheet("background: rgba(255,255,255,0.06);")
    lay.addWidget(sep)
    return lay


def show_terms(parent=None):
    dlg = dialog_frame(parent)
    dlg.setWindowTitle("名词解释")
    lay = dlg_header(dlg, "名词解释", "全部用大白话讲清楚", with_terms=False)
    area = QTextEdit()
    area.setReadOnly(True)
    area.setFixedHeight(320)
    html = ""
    for name, desc in TERMS:
        html += ("<p style='margin:0 0 4px 0'><span style='color:#E8C87A;"
                 "font-weight:700'>%s</span><br>"
                 "<span style='color:#B7BDC8'>%s</span></p>" % (name, desc))
    area.setHtml(html)
    lay.addWidget(area)
    btn = QPushButton("知道了")
    btn.setObjectName("Act")
    btn.setFixedHeight(32)
    btn.clicked.connect(dlg.accept)
    lay.addWidget(btn)
    dlg.setFixedWidth(420)
    dlg.adjustSize()
    dlg.exec_()


def show_help(ctrl):
    dlg = dialog_frame(None)
    lay = dlg_header(dlg, "使用说明", "照着做就能上手", with_terms=True)
    area = QTextEdit()
    area.setReadOnly(True)
    area.setFixedHeight(360)
    area.setHtml("""
<p style="color:#E8C87A;font-weight:700;margin:0 0 6px 0">一分钟上手</p>
<p style="color:#B7BDC8;margin:0 0 10px 0">
1. 程序启动后屏幕就是一张透明的画布，直接在任意软件上按住左键拖动即可画。<br>
2. 点左上角状态胶囊（或按 Ctrl+Alt+D）可切换"绘画中 / 穿透中"。<br>
3. 穿透中：鼠标点击会穿过画笔层，可以正常操作下面的软件，笔迹保留。<br>
4. 画错了点"撤销"；想全部重来点"清空"；想留证据点"截图"。</p>
<p style="color:#E8C87A;font-weight:700;margin:0 0 6px 0">工具栏说明</p>
<p style="color:#B7BDC8;margin:0 0 10px 0">
画笔 / 荧光笔 / 直线 / 箭头 / 矩形 / 椭圆 / 文字 / 橡皮，点一下选中，<br>
选中的按钮会变成金色并显示名称。颜色点一下就换，笔宽拖动滑块或用滚轮调整。</p>
<p style="color:#E8C87A;font-weight:700;margin:0 0 6px 0">快捷键（全局有效）</p>
<p style="color:#B7BDC8;margin:0 0 10px 0">
Ctrl+Alt+D 切换绘画 / 穿透　　Ctrl+Alt+H 隐藏 / 显示笔迹<br>
Ctrl+Alt+Z 撤销　　Ctrl+Alt+Y 重做　　Ctrl+Alt+C 清空<br>
Ctrl+Alt+S 截图存档　　Ctrl+Alt+Q 退出<br>
Ctrl+Alt+1 ~ 8 快速切换 8 个工具<br>
绘画状态下：鼠标右键 = 切换到穿透；滚轮 = 调笔宽</p>
<p style="color:#E8C87A;font-weight:700;margin:0 0 6px 0">注意事项</p>
<p style="color:#B7BDC8;margin:0 0 4px 0">
· 橡皮只擦除你画的笔迹，不会损伤屏幕内容。<br>
· 截图会自动存到程序目录下的"截图存档"文件夹，并在"存档"里留记录。<br>
· 多显示器时整张虚拟桌面都是画布，可在任意一块屏幕上画。</p>
""")
    lay.addWidget(area)
    row = QHBoxLayout()
    btn_folder = QPushButton("打开存档文件夹")
    btn_folder.setObjectName("Act")
    btn_folder.setFixedHeight(32)
    btn_folder.clicked.connect(ctrl.open_archive_folder)
    btn_ok = QPushButton("开始使用")
    btn_ok.setObjectName("Act")
    btn_ok.setFixedHeight(32)
    btn_ok.clicked.connect(dlg.accept)
    row.addWidget(btn_folder)
    row.addWidget(btn_ok)
    lay.addLayout(row)
    dlg.setFixedWidth(470)
    dlg.adjustSize()
    dlg.exec_()


def show_about(ctrl):
    dlg = dialog_frame(None)
    lay = dlg_header(dlg, "关于 " + APP_NAME, "作者信息与运行状态")
    area = QTextEdit()
    area.setReadOnly(True)
    area.setFixedHeight(310)
    uptime = int(time.time() - ctrl.start_time)
    hours, rest = divmod(uptime, 3600)
    minutes, seconds = divmod(rest, 60)
    info = [
        ("程序名称", "%s（%s）" % (APP_NAME, APP_EN)),
        ("当前版本", "v" + VERSION),
        ("程序大小", fmt_size(project_size())),
        ("最后修改", fmt_mtime()),
        ("作者", AUTHOR),
        ("微信", WECHAT),
        ("本次运行", "%d 小时 %d 分 %d 秒" % (hours, minutes, seconds)),
        ("当前笔迹", "%d 笔" % len(ctrl.board.strokes)),
        ("存档记录", "%d 条" % len(ctrl.archive.items)),
        ("本地接口", ctrl.api_text()),
        ("存档目录", ARCHIVE_DIR),
    ]
    html = ""
    for key, val in info:
        html += ("<p style='margin:0 0 6px 0'><span style='color:#8A8F9A'>%s</span><br>"
                 "<span style='color:#E4E7EC'>%s</span></p>" % (key, val))
    html += ("<p style='margin:10px 0 0 0;color:#6E7480;font-size:10px'>"
             "本程序为本地单机工具，不联网、不上传任何屏幕内容。</p>")
    area.setHtml(html)
    lay.addWidget(area)
    row = QHBoxLayout()
    btn_terms = QPushButton("名词解释")
    btn_terms.setObjectName("Act")
    btn_terms.setFixedHeight(32)
    btn_terms.clicked.connect(lambda: show_terms(dlg))
    btn_ok = QPushButton("关闭")
    btn_ok.setObjectName("Act")
    btn_ok.setFixedHeight(32)
    btn_ok.clicked.connect(dlg.accept)
    row.addWidget(btn_terms)
    row.addWidget(btn_ok)
    lay.addLayout(row)
    dlg.setFixedWidth(440)
    dlg.adjustSize()
    dlg.exec_()


class ArchiveDialog(QDialog):
    def __init__(self, ctrl):
        super(ArchiveDialog, self).__init__(None)
        self.ctrl = ctrl
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(STYLE)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame()
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 200))
        card.setGraphicsEffect(shadow)
        card.setStyleSheet("QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                           "stop:0 rgba(22,24,31,250), stop:1 rgba(9,10,14,252));"
                           "border:1px solid rgba(232,200,122,0.22); border-radius:16px;}")
        outer.addWidget(card)
        self.card_layout = QVBoxLayout(card)
        self.card_layout.setContentsMargins(20, 16, 20, 16)
        self.card_layout.setSpacing(10)
        lay = dlg_header(self, "截图存档", "双击一条记录可打开图片")
        self.list = QListWidget()
        self.list.setFixedHeight(330)
        self.list.itemDoubleClicked.connect(self.open_selected)
        lay.addWidget(self.list)

        row = QHBoxLayout()
        btn_open = QPushButton("打开图片")
        btn_open.setObjectName("Act")
        btn_open.setFixedHeight(32)
        btn_open.clicked.connect(self.open_selected)
        btn_folder = QPushButton("打开文件夹")
        btn_folder.setObjectName("Act")
        btn_folder.setFixedHeight(32)
        btn_folder.clicked.connect(self.ctrl.open_archive_folder)
        btn_del = QPushButton("删除")
        btn_del.setObjectName("Act")
        btn_del.setFixedHeight(32)
        btn_del.clicked.connect(self.delete_selected)
        btn_close = QPushButton("关闭")
        btn_close.setObjectName("Act")
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self.accept)
        for btn in (btn_open, btn_folder, btn_del, btn_close):
            row.addWidget(btn)
        lay.addLayout(row)
        self.setFixedWidth(500)
        self.adjustSize()
        self.reload()

    def reload(self):
        self.list.clear()
        for item in self.ctrl.archive.items:
            name = os.path.basename(item.get("file", ""))
            text = "%s    %s    笔迹 %s" % (item.get("time", ""), name,
                                            item.get("strokes", 0))
            qitem = QListWidgetItem(text)
            qitem.setData(Qt.UserRole, item)
            self.list.addItem(qitem)

    def open_selected(self):
        row = self.list.currentRow()
        if row < 0:
            return
        item = self.list.item(row).data(Qt.UserRole)
        path = item.get("file", "")
        if os.path.exists(path):
            os.startfile(path)
        else:
            QMessageBox.warning(self, "文件不存在", "这条记录对应的图片已经被移动或删除。")

    def delete_selected(self):
        row = self.list.currentRow()
        if row < 0:
            return
        self.ctrl.archive.remove(row, delete_file=True)
        self.reload()
        self.ctrl.panel.refresh_meta() if self.ctrl.panel else None


# ---------------------------------------------------------------- 全局热键
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super(HotkeyFilter, self).__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        try:
            if event_type in (b"windows_generic_MSG", "windows_generic_MSG"):
                msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
                if msg.message == WM_HOTKEY:
                    self.callback(int(msg.wParam))
        except Exception:
            pass
        return False, 0


# ---------------------------------------------------------------- 本地接口
API_USAGE = {
    "GET  /status": "查看当前状态（是否绘画、工具、颜色、笔宽、笔迹数）",
    "GET  /history": "查看最近 50 条截图存档",
    "GET  /tools": "查看全部工具与颜色列表",
    "POST /toggle": "在绘画与穿透之间切换",
    "POST /mode": "指定模式，body: {\"paint\": true}",
    "POST /clear": "清空全部笔迹",
    "POST /undo": "撤销一步",
    "POST /redo": "重做一步",
    "POST /save": "合成截图并保存，返回文件路径",
    "POST /tool": "切换工具，body: {\"name\": \"pen\"}",
    "POST /color": "切换颜色，body: {\"value\": \"#FF4D5E\"}",
    "POST /width": "设置笔宽 1-40，body: {\"value\": 6}",
}


def build_api_handler(msg_queue):
    class ApiHandler(BaseHTTPRequestHandler):
        server_version = "ScreenPenAPI/" + VERSION

        def log_message(self, fmt, *args):
            pass

        def _reply(self, data, code=200):
            try:
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass

        def _call(self, cmd, payload=None):
            holder = {"event": threading.Event(), "result": None}
            msg_queue.put((cmd, payload or {}, holder))
            if not holder["event"].wait(2.5):
                return {"ok": False, "error": "主程序无响应"}
            return holder["result"] or {"ok": False, "error": "无结果"}

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            path = self.path.split("?")[0].strip("/")
            if path in ("status", "history", "tools", "ping"):
                self._reply(self._call(path))
            else:
                self._reply({"ok": False, "error": "未知接口", "usage": API_USAGE}, 404)

        def do_POST(self):
            path = self.path.split("?")[0].strip("/")
            length = int(self.headers.get("Content-Length", 0) or 0)
            payload = {}
            if length:
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                except Exception:
                    payload = {}
            self._reply(self._call(path, payload))

    return ApiHandler


# ---------------------------------------------------------------- 主控制器
class ScreenPen(object):
    def __init__(self, api_port=9527):
        self.config = Config(CONFIG_PATH)
        self.archive = Archive(HISTORY_PATH)
        self.tool = self.config.get("tool", "pen")
        if self.tool not in TOOL_MAP:
            self.tool = "pen"
        self.color = self.config.get("color", "#E8C87A")
        self.width = int(self.config.get("width", 4))
        self.paint_mode = not bool(self.config.get("start_through", False))
        self.start_time = time.time()

        self.panel = None
        self.ball = None
        self.board = Board(self)
        self.hotkey_actions = {}
        self.hotkey_filter = HotkeyFilter(self.on_hotkey)
        self.hotkeys_ok = 0

        self.api_port = api_port
        self.api_queue = queue.Queue()
        self.api_server = None
        self.api_ok = False
        self.api_error = ""

        self.timer = None
        self.meta_timer = None

    # -------------------------------------------------- 启动
    def start(self, show_panel=True):
        self.board.show()
        self.board.raise_()
        self.apply_mode(save=False)
        self.install_hotkeys()
        if self.api_port:
            self.start_api()
        if show_panel:
            if self.config.get("collapsed", False):
                self.collapse_panel()
            else:
                self.expand_panel()
        self.timer = QTimer()
        self.timer.timeout.connect(self._pump_api)
        self.timer.start(120)
        self.meta_timer = QTimer()
        self.meta_timer.timeout.connect(self._refresh_meta)
        self.meta_timer.start(30000)

    def ensure_panel(self):
        if self.panel is None:
            self.panel = Panel(self)
            self.panel.adjustSize()
            pos = self.config.get("panel_pos")
            if isinstance(pos, list) and len(pos) == 2:
                self.panel.move(int(pos[0]), int(pos[1]))
            else:
                screen = QApplication.primaryScreen().availableGeometry()
                self.panel.move(screen.right() - Panel.WIDTH - 28, screen.top() + 28)

    def expand_panel(self):
        if self.ball is not None:
            self.ball.hide()
        self.ensure_panel()
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()
        self.config.set("collapsed", False)
        self.refresh_ui()

    def collapse_panel(self):
        if self.panel is not None:
            self.panel.hide()
        if self.ball is None:
            self.ball = DockBall(self)
        pos = self.config.get("ball_pos")
        if isinstance(pos, list) and len(pos) == 2:
            self.ball.move(int(pos[0]), int(pos[1]))
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            self.ball.move(screen.right() - 84, screen.center().y() - 29)
        self.ball.show()
        self.ball.raise_()
        self.config.set("collapsed", True)

    def save_panel_pos(self):
        if self.panel is not None:
            self.config.set("panel_pos", [self.panel.x(), self.panel.y()])

    def save_ball_pos(self):
        if self.ball is not None:
            self.config.set("ball_pos", [self.ball.x(), self.ball.y()])

    # -------------------------------------------------- 模式
    def apply_mode(self, save=True):
        self.board.apply_click_through(not self.paint_mode)
        if self.paint_mode:
            self.board.setCursor(make_cross_cursor())
        else:
            self.board.setCursor(Qt.ArrowCursor)
        try:
            hwnd = int(self.board.winId())
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                                              0x0002 | 0x0001 | 0x0004 | 0x0020)
        except Exception:
            pass
        if save:
            self.config.set("start_through", not self.paint_mode)
        self.refresh_ui()

    def set_mode(self, paint):
        self.paint_mode = bool(paint)
        self.apply_mode()
        self.notify("已切换到%s" % ("绘画" if self.paint_mode else "穿透"))

    def toggle_mode(self):
        self.set_mode(not self.paint_mode)

    def toggle_visible(self):
        self.board.setVisible(not self.board.isVisible())
        self.notify("笔迹层已显示" if self.board.isVisible() else "笔迹层已隐藏")

    # -------------------------------------------------- 参数
    def set_tool(self, key):
        if key not in TOOL_MAP:
            return
        self.tool = key
        self.config.set("tool", key)
        self.refresh_ui()
        self.notify("已选择工具：%s（%s）" % (TOOL_MAP[key][1], TOOL_MAP[key][2]))

    def set_color(self, value):
        color = QColor(value)
        if not color.isValid():
            return
        self.color = value.upper() if value.startswith("#") else value
        self.config.set("color", self.color)
        self.refresh_ui()

    def set_width(self, value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return
        self.width = max(1, min(40, value))
        self.config.set("width", self.width)
        self.refresh_ui()

    def change_width(self, delta):
        self.set_width(self.width + delta)
        self.notify("笔宽 %d" % self.width)

    # -------------------------------------------------- 动作
    def refresh_ui(self):
        if self.panel is not None and self.panel.isVisible():
            self.panel.refresh_state()

    def notify(self, text):
        if self.panel is not None:
            self.panel.notify(text)

    def on_stroke_done(self):
        self.refresh_ui()

    def undo(self):
        ok = self.board.undo()
        self.refresh_ui()
        return ok

    def redo(self):
        ok = self.board.redo()
        self.refresh_ui()
        return ok

    def clear_all(self):
        self.board.clear()
        self.refresh_ui()

    def _refresh_meta(self):
        if self.panel is not None and self.panel.isVisible():
            self.panel.refresh_meta()

    # -------------------------------------------------- 截图保存
    def grab_desktop(self):
        geo = virtual_geometry()
        shot = QImage(geo.size(), QImage.Format_ARGB32)
        shot.fill(Qt.black)
        painter = QPainter(shot)
        for screen in QApplication.screens():
            g = screen.geometry()
            pixmap = screen.grabWindow(0)
            if pixmap.isNull():
                continue
            target = QRect(g.topLeft() - geo.topLeft(), g.size())
            painter.drawPixmap(target, pixmap, QRect(QPoint(0, 0), pixmap.size()))
        painter.drawImage(0, 0, self.board.image)
        painter.end()
        return shot

    def save_shot(self, path=None, silent=False, record=True):
        board_visible = self.board.isVisible()
        panel_visible = self.panel is not None and self.panel.isVisible()
        ball_visible = self.ball is not None and self.ball.isVisible()

        self.board.hide()
        if panel_visible:
            self.panel.hide()
        if ball_visible:
            self.ball.hide()
        QApplication.processEvents()

        try:
            shot = self.grab_desktop()
        except Exception as exc:
            shot = None
            self.notify("截图失败：%s" % exc)

        if board_visible:
            self.board.show()
            self.board.raise_()
        if panel_visible:
            self.panel.show()
            self.panel.raise_()
        if ball_visible:
            self.ball.show()
            self.ball.raise_()
        self.apply_mode(save=False)

        if shot is None:
            return None

        if path is None:
            try:
                os.makedirs(ARCHIVE_DIR, exist_ok=True)
            except OSError:
                pass
            path = os.path.join(ARCHIVE_DIR, "ScreenPen_%s.png" %
                                datetime.now().strftime("%Y%m%d_%H%M%S"))
        else:
            folder = os.path.dirname(path)
            if folder:
                try:
                    os.makedirs(folder, exist_ok=True)
                except OSError:
                    pass

        success = shot.save(path, "PNG")
        if not success:
            self.notify("截图保存失败，请检查目录权限")
            return None
        if record:
            tools_used = sorted(set(s["tool"] for s in self.board.strokes))
            self.archive.add(path, len(self.board.strokes), tools_used)
            self._refresh_meta()
        if not silent:
            self.notify("已保存：%s（点击\"存档\"可查看）" % os.path.basename(path))
            self.refresh_ui()
        return path

    def open_archive_folder(self):
        try:
            os.makedirs(ARCHIVE_DIR, exist_ok=True)
            os.startfile(ARCHIVE_DIR)
        except OSError as exc:
            QMessageBox.warning(None, "无法打开", str(exc))

    def open_archive(self):
        ArchiveDialog(self).exec_()

    def open_help(self):
        show_help(self)

    def open_about(self):
        show_about(self)

    # -------------------------------------------------- 热键
    def install_hotkeys(self):
        try:
            user32 = ctypes.windll.user32
            user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                              ctypes.c_uint, ctypes.c_uint]
            user32.RegisterHotKey.restype = wintypes.BOOL
            user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]

            self.hotkey_actions = {
                1001: self.toggle_mode,
                1002: self.clear_all,
                1003: self.save_shot,
                1004: self.quit_app,
                1005: self.toggle_visible,
                1006: self.undo,
                1007: self.redo,
            }
            vk_map = {
                1001: ord("D"),
                1002: ord("C"),
                1003: ord("S"),
                1004: ord("Q"),
                1005: ord("H"),
                1006: ord("Z"),
                1007: ord("Y"),
            }
            for index in range(len(TOOLS)):
                hid = 1010 + index
                self.hotkey_actions[hid] = (lambda k=TOOLS[index][0]: self.set_tool(k))
                vk_map[hid] = ord(str(index + 1))

            mods = MOD_CONTROL | MOD_ALT | MOD_NOREPEAT
            for hid, vk in vk_map.items():
                if user32.RegisterHotKey(None, hid, mods, vk):
                    self.hotkeys_ok += 1
            QApplication.instance().installNativeEventFilter(self.hotkey_filter)
        except Exception:
            pass

    def unregister_hotkeys(self):
        try:
            user32 = ctypes.windll.user32
            for hid in self.hotkey_actions:
                user32.UnregisterHotKey(None, hid)
            QApplication.instance().removeNativeEventFilter(self.hotkey_filter)
        except Exception:
            pass

    def on_hotkey(self, hid):
        action = self.hotkey_actions.get(hid)
        if action is None:
            return
        try:
            action()
        except Exception:
            pass

    # -------------------------------------------------- 本地接口
    def start_api(self):
        try:
            handler = build_api_handler(self.api_queue)
            self.api_server = ThreadingHTTPServer(("127.0.0.1", self.api_port), handler)
            thread = threading.Thread(target=self.api_server.serve_forever, daemon=True)
            thread.start()
            self.api_ok = True
            self.api_error = ""
        except Exception as exc:
            self.api_ok = False
            self.api_error = str(exc)

    def stop_api(self):
        if self.api_server is not None:
            try:
                self.api_server.shutdown()
                self.api_server.server_close()
            except Exception:
                pass
            self.api_server = None
            self.api_ok = False

    def api_text(self):
        if self.api_ok:
            return "http://127.0.0.1:%d/status（已启用）" % self.api_port
        if self.api_port == 0:
            return "未启用（启动参数 --no-api）"
        return "未启用（%s）" % (self.api_error or "端口被占用")

    def _pump_api(self):
        while True:
            try:
                cmd, payload, holder = self.api_queue.get_nowait()
            except queue.Empty:
                break
            try:
                result = self.handle_api(cmd, payload)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
            holder["result"] = result
            holder["event"].set()

    def api_status(self):
        return {
            "ok": True,
            "app": APP_NAME,
            "app_en": APP_EN,
            "version": VERSION,
            "author": AUTHOR,
            "wechat": WECHAT,
            "paint": self.paint_mode,
            "mode": "paint" if self.paint_mode else "through",
            "tool": self.tool,
            "tool_name": TOOL_MAP.get(self.tool, ("", "", ""))[1],
            "color": self.color,
            "width": self.width,
            "strokes": len(self.board.strokes),
            "redo": len(self.board.redo_stack),
            "saved": len(self.archive.items),
            "uptime": int(time.time() - self.start_time),
        }

    def handle_api(self, cmd, payload=None):
        payload = payload or {}
        if cmd in ("ping", ""):
            return {"ok": True, "pong": True}
        if cmd == "status":
            return self.api_status()
        if cmd == "history":
            return {"ok": True, "items": self.archive.items[:50]}
        if cmd == "tools":
            return {"ok": True,
                    "tools": [{"key": t[0], "name": t[1], "tip": t[2]} for t in TOOLS],
                    "colors": COLORS}
        if cmd == "toggle":
            self.toggle_mode()
            return self.api_status()
        if cmd == "mode":
            self.set_mode(payload.get("paint", True))
            return self.api_status()
        if cmd == "clear":
            self.clear_all()
            return {"ok": True}
        if cmd == "undo":
            return {"ok": self.undo()}
        if cmd == "redo":
            return {"ok": self.redo()}
        if cmd == "save":
            path = self.save_shot()
            return {"ok": bool(path), "file": path}
        if cmd == "tool":
            self.set_tool(str(payload.get("name", "")))
            return self.api_status()
        if cmd == "color":
            self.set_color(str(payload.get("value", "")))
            return self.api_status()
        if cmd == "width":
            self.set_width(payload.get("value", self.width))
            return self.api_status()
        return {"ok": False, "error": "未知命令", "usage": API_USAGE}

    # -------------------------------------------------- 退出
    def quit_app(self):
        try:
            self.config.save()
            self.stop_api()
            self.unregister_hotkeys()
        except Exception:
            pass
        if self.panel is not None:
            self.panel.hide()
        if self.ball is not None:
            self.ball.hide()
        self.board.hide()
        QApplication.instance().quit()


# ---------------------------------------------------------------- 自检
def run_selftest(ctrl, app):
    result = "SELFTEST FAIL"
    try:
        board = ctrl.board
        board.strokes = []
        board.redo_stack = []
        board.strokes.append({
            "tool": "pen",
            "points": [QPoint(120, 120), QPoint(320, 300), QPoint(520, 140)],
            "color": "#FF4D5E", "width": 6, "text": ""})
        board.strokes.append({
            "tool": "arrow",
            "points": [QPoint(540, 340), QPoint(780, 200)],
            "color": "#E8C87A", "width": 5, "text": ""})
        board.strokes.append({
            "tool": "text",
            "points": [QPoint(140, 400)],
            "color": "#38E1E8", "width": 8, "text": "ScreenPen"})
        board.rebuild()

        if not ctrl.undo():
            raise RuntimeError("undo failed")
        if not ctrl.redo():
            raise RuntimeError("redo failed")

        path = os.path.join(tempfile.gettempdir(), "screenpen_selftest.png")
        saved = ctrl.save_shot(path=path, silent=True, record=False)
        size = os.path.getsize(saved) if saved and os.path.exists(saved) else 0
        if size <= 0:
            raise RuntimeError("save failed")

        status = ctrl.handle_api("status")
        tools = ctrl.handle_api("tools")
        if not status.get("ok") or not tools.get("ok"):
            raise RuntimeError("api failed")

        result = ("SELFTEST OK image=%dx%d png=%d bytes strokes=%s hotkeys=%d api=%s"
                  % (board.image.width(), board.image.height(), size,
                     status.get("strokes"), ctrl.hotkeys_ok, ctrl.api_ok))
    except Exception as exc:
        result = "SELFTEST FAIL %s" % exc

    print(result)
    try:
        with open(os.path.join(BASE_DIR, "selftest_result.txt"), "w", encoding="utf-8") as f:
            f.write(result)
    except OSError:
        pass
    QTimer.singleShot(200, ctrl.quit_app)


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Microsoft YaHei", 9))

    api_port = 9527
    for arg in sys.argv:
        if arg.startswith("--api-port="):
            try:
                api_port = int(arg.split("=", 1)[1])
            except ValueError:
                pass
    if "--no-api" in sys.argv:
        api_port = 0

    ctrl = ScreenPen(api_port=api_port)
    ctrl.start()

    if "--selftest" in sys.argv:
        QTimer.singleShot(600, lambda: run_selftest(ctrl, app))

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
