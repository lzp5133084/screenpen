package cn.ecojia.screenpen;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RadialGradient;
import android.graphics.Shader;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;

/**
 * 悬浮球：可拖动，轻点回调 onTap（进入/退出标注模式）。
 */
public class BallView extends View {

    public interface Listener {
        void onTap();

        void onDrag(int dx, int dy);
    }

    private final float dp;
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private Listener listener;
    private float downX, downY, lastX, lastY;
    private boolean dragging;
    private final int slop;

    public BallView(Context context) {
        super(context);
        dp = context.getResources().getDisplayMetrics().density;
        slop = ViewConfiguration.get(context).getScaledTouchSlop();
    }

    public void setListener(Listener l) {
        listener = l;
    }

    @Override
    protected void onDraw(Canvas canvas) {
        float w = getWidth();
        float h = getHeight();
        float cx = w / 2f;
        float cy = h / 2f;
        float r = Math.min(w, h) / 2f;

        // 外发光
        paint.setStyle(Paint.Style.FILL);
        paint.setShader(new RadialGradient(cx, cy, r,
                new int[]{0x33E8C87A, 0x11E8C87A, 0x00E8C87A},
                new float[]{0f, 0.72f, 1f}, Shader.TileMode.CLAMP));
        canvas.drawCircle(cx, cy, r, paint);

        // 球体
        paint.setShader(new LinearGradient(0, 0, w, h,
                new int[]{0xFF1B1D24, 0xFF0A0B0F},
                null, Shader.TileMode.CLAMP));
        canvas.drawCircle(cx, cy, r * 0.86f, paint);

        // 金色描边
        paint.setShader(null);
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(1.6f * dp);
        paint.setColor(0xFFE8C87A);
        canvas.drawCircle(cx, cy, r * 0.86f, paint);

        // 笔尖图形
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(0xFFF7E8BE);
        Path pen = new Path();
        float s = r * 0.86f;
        pen.moveTo(cx - s * 0.42f, cy + s * 0.15f);
        pen.lineTo(cx + s * 0.10f, cy - s * 0.42f);
        pen.lineTo(cx + s * 0.30f, cy - s * 0.20f);
        pen.lineTo(cx - s * 0.22f, cy + s * 0.36f);
        pen.close();
        canvas.drawPath(pen, paint);
        paint.setColor(0xFFE8C87A);
        canvas.drawCircle(cx - s * 0.32f, cy + s * 0.45f, s * 0.11f, paint);
    }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        switch (e.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                downX = lastX = e.getRawX();
                downY = lastY = e.getRawY();
                dragging = false;
                return true;
            case MotionEvent.ACTION_MOVE:
                float dx = e.getRawX() - lastX;
                float dy = e.getRawY() - lastY;
                if (!dragging && Math.hypot(e.getRawX() - downX, e.getRawY() - downY) > slop) {
                    dragging = true;
                }
                if (dragging && listener != null) {
                    listener.onDrag((int) dx, (int) dy);
                }
                lastX = e.getRawX();
                lastY = e.getRawY();
                return true;
            case MotionEvent.ACTION_UP:
                if (!dragging && listener != null) {
                    listener.onTap();
                }
                return true;
        }
        return super.onTouchEvent(e);
    }
}
