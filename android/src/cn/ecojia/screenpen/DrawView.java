package cn.ecojia.screenpen;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PointF;
import android.graphics.RectF;
import android.view.MotionEvent;
import android.view.View;

import java.util.ArrayList;
import java.util.List;

/**
 * 全屏标注层：负责笔迹的绘制、预览与擦除。
 */
public class DrawView extends View {

    public static final String PEN = "pen";
    public static final String HL = "hl";
    public static final String LINE = "line";
    public static final String ARROW = "arrow";
    public static final String RECT = "rect";
    public static final String ELLIPSE = "ellipse";
    public static final String ERASER = "eraser";

    public static final String[] TOOL_KEYS = {PEN, HL, LINE, ARROW, RECT, ELLIPSE, ERASER};
    public static final String[] TOOL_NAMES = {"画笔", "荧光", "直线", "箭头", "矩形", "椭圆", "橡皮"};

    private final List<Stroke> strokes = new ArrayList<Stroke>();
    private final List<Stroke> redoStack = new ArrayList<Stroke>();
    private Stroke current;

    private String tool = PEN;
    private int color = 0xFFE8C87A;
    private final float dp;
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);

    public DrawView(Context context) {
        super(context);
        dp = context.getResources().getDisplayMetrics().density;
        paint.setStrokeJoin(Paint.Join.ROUND);
        paint.setStrokeCap(Paint.Cap.ROUND);
        setLayerType(LAYER_TYPE_HARDWARE, null);
    }

    private static class Stroke {
        String tool;
        int color;
        float width;
        float alpha = 1f;
        final List<PointF> points = new ArrayList<PointF>();
    }

    // ---------------------------------------------------------------- 配置
    public void setTool(String key) {
        tool = key;
        invalidate();
    }

    public String getTool() {
        return tool;
    }

    public void setColor(int c) {
        color = c;
        invalidate();
    }

    public int getColor() {
        return color;
    }

    public boolean hasStrokes() {
        return !strokes.isEmpty();
    }

    // ---------------------------------------------------------------- 操作
    public void undo() {
        if (strokes.isEmpty()) {
            return;
        }
        redoStack.add(strokes.remove(strokes.size() - 1));
        invalidate();
    }

    public void clear() {
        if (strokes.isEmpty()) {
            return;
        }
        redoStack.clear();
        strokes.clear();
        invalidate();
    }

    // ---------------------------------------------------------------- 触摸
    @Override
    public boolean onTouchEvent(MotionEvent e) {
        switch (e.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                if (ERASER.equals(tool)) {
                    eraseAt(e.getX(), e.getY());
                    return true;
                }
                current = new Stroke();
                current.tool = tool;
                current.color = color;
                if (HL.equals(tool)) {
                    current.width = 22 * dp;
                    current.alpha = 0.38f;
                } else {
                    current.width = 3.5f * dp;
                }
                current.points.add(new PointF(e.getX(), e.getY()));
                invalidate();
                return true;

            case MotionEvent.ACTION_MOVE:
                if (ERASER.equals(tool)) {
                    eraseAt(e.getX(), e.getY());
                    return true;
                }
                if (current == null) {
                    return true;
                }
                current.points.add(new PointF(e.getX(), e.getY()));
                invalidate();
                return true;

            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                if (ERASER.equals(tool)) {
                    invalidate();
                    return true;
                }
                if (current != null) {
                    List<PointF> pts = current.points;
                    boolean isFree = PEN.equals(current.tool) || HL.equals(current.tool);
                    boolean tooShort = pts.size() < 2
                            || (isFree && pts.size() < 3)
                            || (!isFree && distance(pts.get(0), pts.get(pts.size() - 1)) < 8 * dp);
                    if (!tooShort) {
                        strokes.add(current);
                        redoStack.clear();
                    }
                    current = null;
                    invalidate();
                }
                return true;
        }
        return super.onTouchEvent(e);
    }

    private void eraseAt(float x, float y) {
        float hit = 26 * dp;
        for (int i = strokes.size() - 1; i >= 0; i--) {
            Stroke s = strokes.get(i);
            PointF last = s.points.get(s.points.size() - 1);
            if (minDistance(s, x, y) <= hit || distance(last, new PointF(x, y)) <= hit * 1.6f) {
                strokes.remove(i);
                redoStack.clear();
                invalidate();
                return;
            }
        }
    }

    private float minDistance(Stroke s, float x, float y) {
        float best = Float.MAX_VALUE;
        for (PointF p : s.points) {
            float d = distance(p, new PointF(x, y));
            if (d < best) {
                best = d;
            }
        }
        return best;
    }

    private static float distance(PointF a, PointF b) {
        float dx = a.x - b.x;
        float dy = a.y - b.y;
        return (float) Math.sqrt(dx * dx + dy * dy);
    }

    // ---------------------------------------------------------------- 绘制
    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        for (Stroke s : strokes) {
            drawStroke(canvas, s);
        }
        if (current != null) {
            drawStroke(canvas, current);
        }
    }

    private void drawStroke(Canvas canvas, Stroke s) {
        if (s.points.isEmpty()) {
            return;
        }
        paint.setColor(s.color);
        paint.setAlpha((int) (255 * s.alpha));
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(s.width);

        PointF a = s.points.get(0);
        PointF b = s.points.get(s.points.size() - 1);

        if (PEN.equals(s.tool) || HL.equals(s.tool)) {
            Path path = new Path();
            path.moveTo(a.x, a.y);
            for (int i = 1; i < s.points.size(); i++) {
                PointF p = s.points.get(i);
                path.lineTo(p.x, p.y);
            }
            canvas.drawPath(path, paint);
            return;
        }

        if (LINE.equals(s.tool)) {
            canvas.drawLine(a.x, a.y, b.x, b.y, paint);
        } else if (ARROW.equals(s.tool)) {
            canvas.drawLine(a.x, a.y, b.x, b.y, paint);
            drawArrowHead(canvas, a, b, s.width);
        } else if (RECT.equals(s.tool)) {
            canvas.drawRect(Math.min(a.x, b.x), Math.min(a.y, b.y),
                    Math.max(a.x, b.x), Math.max(a.y, b.y), paint);
        } else if (ELLIPSE.equals(s.tool)) {
            canvas.drawOval(new RectF(Math.min(a.x, b.x), Math.min(a.y, b.y),
                    Math.max(a.x, b.x), Math.max(a.y, b.y)), paint);
        }
    }

    private void drawArrowHead(Canvas canvas, PointF a, PointF b, float width) {
        double angle = Math.atan2(b.y - a.y, b.x - a.x);
        float len = Math.max(width * 4.2f, 16 * dp);
        float spread = (float) Math.toRadians(26);
        float x1 = (float) (b.x - len * Math.cos(angle - spread));
        float y1 = (float) (b.y - len * Math.sin(angle - spread));
        float x2 = (float) (b.x - len * Math.cos(angle + spread));
        float y2 = (float) (b.y - len * Math.sin(angle + spread));

        Path head = new Path();
        head.moveTo(b.x, b.y);
        head.lineTo(x1, y1);
        head.lineTo(x2, y2);
        head.close();
        paint.setStyle(Paint.Style.FILL);
        canvas.drawPath(head, paint);
        paint.setStyle(Paint.Style.STROKE);
    }
}
